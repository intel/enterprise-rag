#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Smoke-test the pipeline composer against the real pipeline definitions.

compose_pipeline.py runs on every application-layer install, but its failures only
surface at deploy time: a Jinja sandbox rejection, a renamed shared step, a broken
loader precedence or a dropped `resources:` key all produce a valid-looking run until
Ansible invokes the script. These tests exercise the shipped definitions in-process so
that class of breakage fails in CI instead.

The `llm` step is the one shared step whose resources come from pipeline.yaml rather
than the step file, so rendering it covers the `required` filter, the `tojson` filter
under SandboxedEnvironment, shared-vs-local template resolution and the resource
aggregation in a single pass. No cluster or network is contacted.
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PIPELINES_DIR = _REPO_ROOT / "deployment" / "pipelines"
_COMPOSER_PATH = _REPO_ROOT / "deployment" / "scripts" / "compose_pipeline.py"

# Modular pipelines (config.yaml + pipeline.yaml). Thin flavours such as audioqna and
# pl_chatqna carry no pipeline.yaml of their own and compose through their base type.
_MODULAR_PIPELINES = ["chatqna", "docsum", "translation"]


def _load_composer():
    """Import compose_pipeline.py by path - deployment/scripts is not an importable package."""
    spec = importlib.util.spec_from_file_location("compose_pipeline", _COMPOSER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


composer = _load_composer()


def _template_vars(pipeline):
    """Build the composer's template_vars the way app_pipeline/tasks/install.yaml does.

    The role passes pipeline.yaml's `endpoints` through verbatim, so reading it here keeps
    the test honest: a pipeline that stops declaring what its steps consume fails.
    """
    meta = yaml.safe_load((_PIPELINES_DIR / pipeline / "pipeline.yaml").read_text())
    return {"endpoints": meta["endpoints"]}


@pytest.mark.parametrize("pipeline", _MODULAR_PIPELINES)
def test_base_flow_composes_with_llm_step(pipeline):
    """Every modular pipeline's base flow renders, and the llm step survives the sandbox."""
    gmc, resources = composer.compose_pipeline(
        _PIPELINES_DIR / pipeline, [], _template_vars(pipeline)
    )

    assert gmc["kind"] == "GMConnector"
    assert gmc["metadata"]["labels"]["gmc/pipeline-type"] == pipeline
    assert gmc["metadata"]["labels"]["gmc/variant"] == "base"

    steps = gmc["spec"]["nodes"]["root"]["steps"]
    llm_steps = [s for s in steps if s["name"] == "Llm"]
    assert len(llm_steps) == 1, f"expected exactly one Llm step, got {[s['name'] for s in steps]}"
    assert llm_steps[0]["internalService"]["serviceName"] == "llm-svc"

    # `tojson` renders the requests/limits maps; a sandbox or filter regression would
    # either raise or leave the values unparsed.
    llm_usvc = resources["services"]["llm-usvc"]
    assert isinstance(llm_usvc["resources"]["requests"], dict)
    assert isinstance(llm_usvc["resources"]["limits"], dict)
    assert set(llm_usvc["resources"]["requests"]) == {"cpu", "memory"}


def test_llm_resources_come_from_pipeline_yaml():
    """The llm step is sized per pipeline - assert the values reach the Helm overlay."""
    endpoints = _template_vars("chatqna")["endpoints"]
    _, resources = composer.compose_pipeline(
        _PIPELINES_DIR / "chatqna", [], {"endpoints": endpoints}
    )

    expected = yaml.safe_load(
        (_PIPELINES_DIR / "chatqna" / "pipeline.yaml").read_text()
    )["endpoints"]["llm"]["resources"]
    llm_usvc = resources["services"]["llm-usvc"]
    assert llm_usvc["replicas"] == expected["replicas"]
    assert llm_usvc["resources"]["requests"] == expected["requests"]
    assert llm_usvc["resources"]["limits"] == expected["limits"]


def test_chatqna_base_flow_order_and_resource_keys():
    """Resources are aggregated for active steps only, one <usvc> key per step."""
    gmc, resources = composer.compose_pipeline(
        _PIPELINES_DIR / "chatqna", [], _template_vars("chatqna")
    )

    assert [s["name"] for s in gmc["spec"]["nodes"]["root"]["steps"]] == [
        "Embedding",
        "Retriever",
        "Reranking",
        "PromptTemplate",
        "LLMGuardInput",
        "Llm",
    ]
    assert sorted(resources["services"]) == [
        "embedding-usvc",
        "in-guard-usvc",
        "llm-usvc",
        "prompt-template-usvc",
        "reranking-usvc",
        "retriever-usvc",
    ]
    # Unselected variant services must not leak into the overlay.
    assert "query-rewrite-usvc" not in resources["services"]


def test_variant_is_inserted_at_its_anchor():
    """query-rewrite declares insert_before: embedding and brings its own resources."""
    template_vars = _template_vars("chatqna")
    template_vars["pipeline_variant"] = "query-rewrite"
    gmc, resources = composer.compose_pipeline(
        _PIPELINES_DIR / "chatqna", ["query-rewrite"], template_vars
    )

    names = [s["name"] for s in gmc["spec"]["nodes"]["root"]["steps"]]
    assert names.index("QueryRewrite") < names.index("Embedding")
    assert "query-rewrite-usvc" in resources["services"]
    assert gmc["metadata"]["labels"]["gmc/variant"] == "query-rewrite"


def test_retrieve_rerank_variant_drops_the_generation_tail():
    """retrieve-rerank replaces the tail with nothing, leaving a retrieval-only flow.

    This is the flow the MCP gateway needs (EDP's /api/retrieve calls retriever-svc then
    reranking-svc), and mcp_enabled is derived from exactly these two services being
    present, so a regression here silently disables MCP.
    """
    template_vars = _template_vars("chatqna")
    template_vars["pipeline_variant"] = "retrieve-rerank"
    gmc, resources = composer.compose_pipeline(
        _PIPELINES_DIR / "chatqna", ["retrieve-rerank"], template_vars
    )

    steps = gmc["spec"]["nodes"]["root"]["steps"]
    assert [s["name"] for s in steps] == ["Embedding", "Retriever", "Reranking"]
    assert [s["internalService"]["serviceName"] for s in steps] == [
        "embedding-svc",
        "retriever-svc",
        "reranking-svc",
    ]
    # A variant rendering no steps contributes no resources, so the replaced services
    # must fall out of the overlay entirely rather than linger at replicas: 0.
    assert sorted(resources["services"]) == [
        "embedding-usvc",
        "reranking-usvc",
        "retriever-usvc",
    ]
    assert gmc["metadata"]["labels"]["gmc/variant"] == "retrieve-rerank"


def test_missing_llm_resources_fails_with_actionable_message():
    """The `required` filter must name the missing key, not raise a bare attribute error."""
    endpoints = _template_vars("chatqna")["endpoints"]
    endpoints["llm"].pop("resources")

    with pytest.raises(ValueError, match="endpoints.llm.resources missing in pipeline.yaml"):
        composer.compose_pipeline(_PIPELINES_DIR / "chatqna", [], {"endpoints": endpoints})


def test_unknown_variant_fails_with_the_path_it_looked_for():
    with pytest.raises(FileNotFoundError, match="Variant directory not found"):
        composer.compose_pipeline(
            _PIPELINES_DIR / "chatqna", ["no-such-variant"], _template_vars("chatqna")
        )


def _run_cli(variants_csv, pipeline="chatqna"):
    """Invoke the CLI entry point the way app_pipeline does, capturing its exit."""
    template_vars = _template_vars(pipeline)
    template_vars["pipeline_type"] = pipeline
    template_vars["pipeline_variant"] = variants_csv or "base"
    argv = [
        str(_COMPOSER_PATH),
        str(_PIPELINES_DIR / pipeline),
        variants_csv,
        json.dumps(template_vars),
    ]
    with patch.object(sys, "argv", argv), pytest.raises(SystemExit) as exit_info:
        composer.main()
    return exit_info.value.code


def test_cli_composes_base_flow(capsys):
    """The happy path exits 0 by falling off the end of main(), not via SystemExit."""
    template_vars = _template_vars("chatqna")
    template_vars["pipeline_type"] = "chatqna"
    template_vars["pipeline_variant"] = "base"
    argv = [str(_COMPOSER_PATH), str(_PIPELINES_DIR / "chatqna"), "", json.dumps(template_vars)]
    with patch.object(sys, "argv", argv):
        composer.main()

    gmc = yaml.safe_load(capsys.readouterr().out)
    assert gmc["kind"] == "GMConnector"


def test_cli_collapses_a_repeated_variant(capsys):
    """A duplicated variant must not apply twice - dedupe keeps it a single insertion."""
    template_vars = _template_vars("chatqna")
    template_vars["pipeline_variant"] = "query-rewrite"
    argv = [
        str(_COMPOSER_PATH),
        str(_PIPELINES_DIR / "chatqna"),
        "query-rewrite,query-rewrite",
        json.dumps(template_vars),
    ]
    with patch.object(sys, "argv", argv):
        composer.main()

    gmc = yaml.safe_load(capsys.readouterr().out)
    names = [s["name"] for s in gmc["spec"]["nodes"]["root"]["steps"]]
    assert names.count("QueryRewrite") == 1


def test_cli_rejects_multiple_variants(capsys):
    """Several variants have no defined application order - fail loudly, don't guess."""
    assert _run_cli("query-rewrite,hybrid-retrieval") == 1
    assert "multiple variants are not supported yet" in capsys.readouterr().err
