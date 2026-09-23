# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from comps.system_fingerprint.utils.object_document_mapper import (
    DocsumParams,
    LLMParams,
    QueryRewriteParams,
    RerankerParams,
    RetrieverParams,
)
from comps.system_fingerprint.utils.erag_system_fingerprint import (
    EXTRA_SCOPED_SEEDS,
    GROUP_MODELS,
    NESTED_GROUPS,
    NOTIFY_CHANNEL,
    SCHEMA_DDL,
    SCHEMA_VERSION,
    STATEMENT_TIMEOUT_SECONDS,
    VALID_GROUPS,
    EragSystemFingerprintController,
    _deep_merge,
    from_wire_shape,
    params_kind_catalog,
    to_wire_shape,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

# Minimal stand-in for a docarray ComponentArgument. The optional params_kind
# mirrors the proto field and defaults to None, matching an item that omits it.
ComponentArgument = namedtuple(
    "ComponentArgument", ["name", "data", "params_kind"], defaults=[None])


class _AsyncCtx:
    """Async context manager returning a fixed value on ``__aenter__``."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def make_conn():
    """Builds a mock asyncpg connection with async DB methods."""
    conn = MagicMock(name="conn")
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value=None)
    conn.executemany = AsyncMock(return_value=None)
    # conn.transaction() must be an async context manager (sync call).
    conn.transaction = MagicMock(return_value=_AsyncCtx(None))
    return conn


def attach_pool(controller, conn):
    """Wires a mock pool onto the controller whose acquire() yields conn."""
    pool = MagicMock(name="pool")
    pool.acquire = MagicMock(return_value=_AsyncCtx(conn))
    controller.pool = pool
    return pool


def make_controller(template_language="en", pipeline="default", tenant="_global"):
    return EragSystemFingerprintController(
        host="localhost",
        port=5432,
        db_name="fingerprint",
        pipeline=pipeline,
        tenant=tenant,
        template_language=template_language,
    )


@pytest.fixture
def controller():
    return make_controller()


# ---------------------------------------------------------------------------
# 1. _deep_merge (pure function)
# ---------------------------------------------------------------------------

def test_deep_merge_preserves_sibling_fields():
    base = {"max_new_tokens": 1024, "top_k": 10, "temperature": 0.01}
    patch = {"max_new_tokens": 512}

    merged = _deep_merge(base, patch)

    assert merged["max_new_tokens"] == 512, "Patched field should be updated."
    assert merged["top_k"] == 10, "Sibling field must be preserved."
    assert merged["temperature"] == 0.01, "Sibling field must be preserved."


def test_deep_merge_recurses_into_nested_dicts():
    base = {
        "anonymize": {"enabled": False, "threshold": 0.7},
        "toxicity": {"enabled": True, "threshold": 0.5},
    }
    patch = {"anonymize": {"enabled": True}}

    merged = _deep_merge(base, patch)

    assert merged["anonymize"]["enabled"] is True, "Nested field should be updated."
    assert merged["anonymize"]["threshold"] == 0.7, \
        "Sibling nested field must be preserved."
    assert merged["toxicity"] == {"enabled": True, "threshold": 0.5}, \
        "Sibling scanner must be preserved untouched."


def test_deep_merge_does_not_mutate_inputs():
    base = {"anonymize": {"enabled": False, "threshold": 0.7}, "top_k": 10}
    patch = {"anonymize": {"enabled": True}, "top_k": 5}
    base_snapshot = json.loads(json.dumps(base))
    patch_snapshot = json.loads(json.dumps(patch))

    _deep_merge(base, patch)

    assert base == base_snapshot, "base must not be mutated by _deep_merge."
    assert patch == patch_snapshot, "patch must not be mutated by _deep_merge."


# ---------------------------------------------------------------------------
# 2. _default_groups / constructor validation
# ---------------------------------------------------------------------------

def test_default_groups_has_exactly_the_expected_keys(controller):
    defaults = controller._default_groups()

    assert set(defaults.keys()) == {
        "llm",
        "retriever",
        "reranker",
        "query_rewrite",
        "docsum",
        "prompt_template",
        "input_guard",
        "output_guard",
        "dataprep_guard",
    }, "Default groups must be exactly the known parameter groups."


def test_default_groups_llm_defaults(controller):
    llm = controller._default_groups()["llm"]

    assert llm["max_new_tokens"] == 1024, "Default LLM max_new_tokens should be 1024."
    assert llm["top_k"] == 10, "Default LLM top_k should be 10."
    assert llm["temperature"] == 0.01, "Default LLM temperature should be 0.01."


def test_default_groups_retriever_defaults(controller):
    retriever = controller._default_groups()["retriever"]

    assert retriever["search_type"] == "similarity"
    assert retriever["k"] == 10


def test_default_groups_english_prompt_template():
    controller = make_controller(template_language="en")
    system = controller._default_groups()["prompt_template"]["system_prompt_template"]

    assert "helpful, respectful, and honest assistant" in system, \
        "English template must be used for template_language='en'."
    assert "asystentem" not in system, "English template must not contain Polish text."


def test_default_groups_polish_prompt_template():
    controller = make_controller(template_language="pl")
    system = controller._default_groups()["prompt_template"]["system_prompt_template"]

    assert "asystentem" in system, \
        "Polish template must be used for template_language='pl'."


def test_template_language_is_case_insensitive():
    controller = make_controller(template_language="PL")
    system = controller._default_groups()["prompt_template"]["system_prompt_template"]

    assert "asystentem" in system, "Template language should be normalised to lower case."


def test_unsupported_template_language_raises_value_error():
    with pytest.raises(ValueError, match="Unsupported template language"):
        make_controller(template_language="de")


# ---------------------------------------------------------------------------
# 3. store_arguments
# ---------------------------------------------------------------------------

def _data_write_calls(conn):
    """Returns INSERT-into-fingerprint_config execute calls (the data writes)."""
    calls = []
    for call in conn.execute.await_args_list:
        sql = call.args[0]
        if "INSERT INTO fingerprint_config" in sql:
            calls.append(call)
    return calls


def _seed_batch_calls(conn):
    """Returns the executemany seed calls: (sql, [row, ...]) per invocation."""
    calls = []
    for call in conn.executemany.await_args_list:
        sql = call.args[0]
        if "INSERT INTO fingerprint_config" in sql:
            calls.append(call)
    return calls


def _seed_rows(conn):
    """Flattens every seeded row across all executemany calls into one list."""
    rows = []
    for call in _seed_batch_calls(conn):
        rows.extend(call.args[1])
    return rows


@pytest.mark.asyncio
async def test_store_arguments_skips_key_without_resolvable_kind(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    # A free-form key with no stored row and no supplied kind cannot be resolved
    # to a value model, so it is silently ignored.
    await controller.store_arguments([
        ComponentArgument(name="llm_primary", data={"max_new_tokens": 512}),
    ])

    assert _data_write_calls(conn) == [], \
        "A key with no resolvable kind must not trigger a write."


@pytest.mark.asyncio
async def test_store_arguments_writes_custom_key_with_supplied_kind(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)  # no stored row yet
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    # A custom key addressed with an explicit kind persists under that key,
    # validated through the kind's value model.
    await controller.store_arguments([
        ComponentArgument(
            name="llm_primary", data={"max_new_tokens": 512}, params_kind="llm"),
    ])

    writes = _data_write_calls(conn)
    assert len(writes) == 1, "A custom key with a valid kind must be written."
    call = writes[0]
    assert call.args[3] == "llm_primary", "The row must be keyed on the custom key."
    assert call.args[4] == "llm", "params_kind must be the supplied kind."
    stored = json.loads(call.args[5])
    assert stored["max_new_tokens"] == 512
    # The kind's defaults fill the fields the caller did not supply.
    assert stored["top_k"] == LLMParams().top_k


@pytest.mark.asyncio
async def test_store_arguments_reuses_stored_kind_for_custom_key(controller):
    conn = make_conn()
    existing = LLMParams().model_dump()
    # The key already exists with kind "llm"; a later write need not repeat it.
    conn.fetchrow = AsyncMock(
        return_value={"values": json.dumps(existing), "params_kind": "llm"})
    conn.fetchval = AsyncMock(return_value=2)
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="llm_secondary", data={"max_new_tokens": 256}),
    ])

    writes = _data_write_calls(conn)
    assert len(writes) == 1
    call = writes[0]
    assert call.args[3] == "llm_secondary"
    assert call.args[4] == "llm", "The stored kind must be reused when none is supplied."
    assert json.loads(call.args[5])["max_new_tokens"] == 256


@pytest.mark.asyncio
async def test_store_arguments_rejects_unknown_supplied_kind(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="Unknown params_kind"):
        await controller.store_arguments([
            ComponentArgument(
                name="llm_primary", data={"max_new_tokens": 512},
                params_kind="not_a_kind"),
        ])


@pytest.mark.parametrize("bad_key", ["llm.primary", "llm primary", "llm*", "llm>"])
@pytest.mark.asyncio
async def test_store_arguments_rejects_params_key_outside_charset(controller, bad_key):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    # A key the KV projection would drop is rejected at write time so the write
    # cannot silently fail to propagate.
    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_/=-\]"):
        await controller.store_arguments([
            ComponentArgument(
                name=bad_key, data={"max_new_tokens": 512}, params_kind="llm"),
        ])

    assert _data_write_calls(conn) == [], \
        "A params_key outside the allowed charset must be rejected before any write."


@pytest.mark.asyncio
async def test_store_arguments_rejects_kind_mismatch_on_canonical_key(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    # A canonical key names its own kind; a contradicting explicit kind would
    # store an inconsistent row and must be rejected.
    with pytest.raises(ValueError, match="does not match canonical"):
        await controller.store_arguments([
            ComponentArgument(
                name="llm", data={"max_new_tokens": 512}, params_kind="retriever"),
        ])


@pytest.mark.asyncio
async def test_store_arguments_rejects_kind_change_on_existing_key(controller):
    conn = make_conn()
    existing = LLMParams().model_dump()
    # The key already exists as an "llm" row; supplying a different kind would
    # repurpose the row and drop its fields, so it must be rejected.
    conn.fetchrow = AsyncMock(
        return_value={"values": json.dumps(existing), "params_kind": "llm"})
    conn.fetchval = AsyncMock(return_value=1)
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="does not match the stored kind"):
        await controller.store_arguments([
            ComponentArgument(
                name="llm_primary", data={"top_n": 5}, params_kind="reranker"),
        ])


@pytest.mark.asyncio
async def test_store_arguments_two_instances_get_distinct_values(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="llm_primary", data={"max_new_tokens": 1024},
                          params_kind="llm"),
        ComponentArgument(name="llm_secondary", data={"max_new_tokens": 512},
                          params_kind="llm"),
    ])

    writes = _data_write_calls(conn)
    assert len(writes) == 2, "Each instance key must be written to its own row."
    by_key = {call.args[3]: json.loads(call.args[5]) for call in writes}
    assert by_key["llm_primary"]["max_new_tokens"] == 1024
    assert by_key["llm_secondary"]["max_new_tokens"] == 512


@pytest.mark.asyncio
async def test_store_arguments_raises_value_error_on_invalid_data(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    # A value that fails the group model must surface as ValueError (the handler
    # maps it to a 400); pydantic ValidationError is a ValueError subclass.
    with pytest.raises(ValueError):
        await controller.store_arguments([
            ComponentArgument(name="llm", data={"max_new_tokens": "not-an-int"}),
        ])


@pytest.mark.asyncio
async def test_store_arguments_skips_none_data(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="llm", data=None),
    ])

    assert _data_write_calls(conn) == [], \
        "A group with data=None must be skipped."


@pytest.mark.asyncio
async def test_store_arguments_merges_and_preserves_siblings(controller):
    conn = make_conn()
    # Existing stored llm values (full default set) returned as a JSON string.
    existing = LLMParams().model_dump()
    conn.fetchrow = AsyncMock(
        return_value={"values": json.dumps(existing), "params_kind": "llm"})
    conn.fetchval = AsyncMock(return_value=3)  # current max version
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="llm", data={"max_new_tokens": 512}),
    ])

    writes = _data_write_calls(conn)
    assert len(writes) == 1, "A changed recognised group should be written once."

    call = writes[0]
    assert "ON CONFLICT (pipeline, tenant, params_key)" in call.args[0], \
        "The write must be an upsert."
    # Positional args: pipeline, tenant, params_key, params_kind, values_json, ...
    values_json = call.args[5]
    stored = json.loads(values_json)
    assert stored["max_new_tokens"] == 512, "Patched field must be persisted."
    assert stored["top_k"] == existing["top_k"], "Sibling field must be preserved."
    assert stored["temperature"] == existing["temperature"], \
        "Sibling field must be preserved."
    # Version bumps to current max + 1.
    assert call.args[6] == SCHEMA_VERSION, "schema_version should be written."
    assert call.args[7] == 4, "version must be bumped to max(version)+1."


@pytest.mark.asyncio
async def test_store_arguments_persists_docsum_and_preserves_siblings(controller):
    conn = make_conn()
    existing = DocsumParams().model_dump()
    conn.fetchrow = AsyncMock(
        return_value={"values": json.dumps(existing), "params_kind": "docsum"})
    conn.fetchval = AsyncMock(return_value=2)
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="docsum", data={"summary_type": "refine"}),
    ])

    writes = _data_write_calls(conn)
    assert len(writes) == 1, "A changed docsum group should be written once."
    call = writes[0]
    assert call.args[3] == "docsum", "params_kind must be docsum."
    # docsum is flat, so the stored value carries its fields at the top level.
    stored = json.loads(call.args[5])
    assert stored["summary_type"] == "refine", "Patched field must be persisted."
    assert stored["max_new_tokens"] == existing["max_new_tokens"], \
        "Sibling field must be preserved."
    assert stored["stream"] == existing["stream"], "Sibling field must be preserved."


@pytest.mark.asyncio
@pytest.mark.parametrize("summary_type", ["map_reduce", "refine", "stuff"])
async def test_store_arguments_accepts_supported_docsum_summary_type(controller, summary_type):
    conn = make_conn()
    conn.fetchrow = AsyncMock(
        return_value={"values": json.dumps(DocsumParams().model_dump()),
                      "params_kind": "docsum"})
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="docsum", data={"summary_type": summary_type}),
    ])

    if summary_type == "map_reduce":
        # Equal to the stored default, so the write is skipped as a duplicate.
        assert _data_write_calls(conn) == []
    else:
        stored = json.loads(_data_write_calls(conn)[0].args[5])
        assert stored["summary_type"] == summary_type, \
            "A supported summary_type must be persisted."


@pytest.mark.asyncio
async def test_store_arguments_rejects_unsupported_docsum_summary_type(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    # summary_type is constrained to the docsum service's supported chain types,
    # so an unsupported value is rejected at write time (ValidationError is a
    # ValueError subclass, which the handler maps to a 400) instead of failing
    # later in the docsum microservice.
    with pytest.raises(ValueError):
        await controller.store_arguments([
            ComponentArgument(name="docsum", data={"summary_type": "bogus"}),
        ])
    assert _data_write_calls(conn) == [], \
        "An unsupported summary_type must not be written."


@pytest.mark.asyncio
async def test_store_arguments_persists_prompt_template(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)  # no stored prompt_template yet
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(
            name="prompt_template",
            data={"system_prompt_template": "always answer 1234\n{reranked_docs}\n"},
        ),
    ])

    writes = _data_write_calls(conn)
    assert len(writes) == 1, \
        "prompt_template is a writable group and must be persisted."
    call = writes[0]
    assert call.args[3] == "prompt_template", "params_key must be prompt_template."
    stored = json.loads(call.args[5])
    assert stored["system_prompt_template"] == "always answer 1234\n{reranked_docs}\n"
    # The language-dependent default fills the untouched sibling field.
    assert "user_prompt_template" in stored, \
        "Merge with the language default must keep the sibling field."


@pytest.mark.asyncio
async def test_store_arguments_takes_advisory_lock(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="llm", data={"max_new_tokens": 512}),
    ])

    lock_calls = [
        call for call in conn.execute.await_args_list
        if "pg_advisory_xact_lock" in call.args[0]
    ]
    assert lock_calls, \
        "A transaction-scoped advisory lock must serialize concurrent writers."
    # The lock key must not rely on a text separator (a Postgres text value
    # cannot contain a NUL byte); the two-key hashtext form is used instead.
    for call in lock_calls:
        assert "hashtext(" in call.args[0]
        assert all("\x00" not in str(a) for a in call.args[1:])


@pytest.mark.asyncio
async def test_check_and_ingest_defaults_seeds_at_current_version(controller):
    conn = make_conn()
    # A pipeline whose existing rows have already advanced to version 7.
    conn.fetchval = AsyncMock(return_value=7)
    attach_pool(controller, conn)

    await controller._check_and_ingest_defaults()

    seed_calls = _data_write_calls(conn)
    assert seed_calls, "Defaults must be seeded."
    for call in seed_calls:
        assert call.args[7] == 8, \
            "Newly seeded rows must use the current next version, not 1, " \
            "so the monotonic-per-(pipeline,tenant) invariant holds."


@pytest.mark.asyncio
async def test_check_and_ingest_defaults_seeds_extra_scoped_rows(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    await controller._check_and_ingest_defaults()

    # execute args are (sql, pipeline, tenant, params_key, params_kind, ...).
    seeded_scopes = {
        (call.args[1], call.args[2], call.args[3]) for call in _data_write_calls(conn)
    }
    for pipeline, tenant, params_key in EXTRA_SCOPED_SEEDS:
        assert (pipeline, tenant, params_key) in seeded_scopes, \
            f"Extra scoped seed ({pipeline}, {tenant}, {params_key}) must be seeded " \
            "so a consumer of that scope finds its row on first read."


@pytest.mark.asyncio
async def test_check_and_ingest_defaults_extra_seed_is_idempotent(controller):
    # Two consecutive init passes issue the same ON CONFLICT DO NOTHING inserts,
    # so a restart re-seeds without overwriting a row an admin has since edited.
    conn = make_conn()
    attach_pool(controller, conn)

    await controller._check_and_ingest_defaults()
    await controller._check_and_ingest_defaults()

    for call in _data_write_calls(conn):
        assert "ON CONFLICT (pipeline, tenant, params_key)" in call.args[0]
        assert "DO NOTHING" in call.args[0]


@pytest.mark.asyncio
async def test_extra_scoped_seeds_are_wire_shaped(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    await controller._check_and_ingest_defaults()

    for pipeline, tenant, params_key in EXTRA_SCOPED_SEEDS:
        row = next(
            call for call in _data_write_calls(conn)
            if (call.args[1], call.args[2], call.args[3]) == (pipeline, tenant, params_key)
        )
        stored = json.loads(row.args[5])
        expected = to_wire_shape(params_key, controller._default_values_for(params_key))
        assert stored == expected, \
            "An extra scoped seed must be stored in wire shape, like every other row."


@pytest.mark.asyncio
async def test_init_async_closes_pool_on_setup_failure(controller, monkeypatch):
    conn = make_conn()
    pool = attach_pool(controller, conn)
    pool.close = AsyncMock()

    async def fake_create_pool(*args, **kwargs):
        return pool

    monkeypatch.setattr(
        "comps.system_fingerprint.utils.erag_system_fingerprint.asyncpg.create_pool",
        fake_create_pool,
    )
    monkeypatch.setattr(
        controller, "_setup_schema", AsyncMock(side_effect=RuntimeError("ddl boom")))

    with pytest.raises(Exception, match="Failed to initialize Postgres"):
        await controller.init_async()

    pool.close.assert_awaited(), \
        "The pool must be closed when setup fails, to avoid leaking connections."


@pytest.mark.asyncio
async def test_connect_with_retry_retries_transient_errors(controller, monkeypatch):
    # Two transient failures, then a successful connect on the third attempt.
    attempts = {"n": 0}
    sentinel_pool = object()

    async def flaky_create_pool(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("db still starting")
        return sentinel_pool

    monkeypatch.setattr(
        "comps.system_fingerprint.utils.erag_system_fingerprint.asyncpg.create_pool",
        flaky_create_pool,
    )
    # Do not actually sleep between attempts.
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(
        "comps.system_fingerprint.utils.erag_system_fingerprint.asyncio.sleep", no_sleep)

    pool = await controller._connect_with_retry()

    assert pool is sentinel_pool, "A transient failure must be retried until it succeeds."
    assert attempts["n"] == 3, "The connect must be retried on transient errors."


@pytest.mark.asyncio
async def test_connect_with_retry_fails_fast_on_config_error(controller, monkeypatch):
    attempts = {"n": 0}

    async def bad_credentials(*args, **kwargs):
        attempts["n"] += 1
        raise asyncpg.InvalidPasswordError("bad password")

    monkeypatch.setattr(
        "comps.system_fingerprint.utils.erag_system_fingerprint.asyncpg.create_pool",
        bad_credentials,
    )

    with pytest.raises(asyncpg.InvalidPasswordError):
        await controller._connect_with_retry()

    assert attempts["n"] == 1, \
        "A configuration/auth error must fail fast without retrying."


@pytest.mark.asyncio
async def test_connect_with_retry_bounds_pooled_statements(controller, monkeypatch):
    captured = {}

    async def fake_create_pool(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(
        "comps.system_fingerprint.utils.erag_system_fingerprint.asyncpg.create_pool",
        fake_create_pool,
    )

    await controller._connect_with_retry()

    assert captured.get("command_timeout") == STATEMENT_TIMEOUT_SECONDS, \
        "The pool must bound every pooled statement so a stuck query cannot starve it."


@pytest.mark.asyncio
async def test_store_arguments_skips_duplicate(controller, monkeypatch):
    conn = make_conn()
    conn.fetchval = AsyncMock(return_value=1)
    attach_pool(controller, conn)

    # Existing value equals the canonicalised merge result -> duplicate.
    existing = LLMParams().model_dump()

    async def fake_read_group(_conn, _params_key, _pipeline=None, _tenant=None):
        return {"values": existing, "params_kind": "llm"}

    monkeypatch.setattr(controller, "_read_group", fake_read_group)

    # Patch with values identical to existing -> no net change.
    await controller.store_arguments([
        ComponentArgument(name="llm", data={"max_new_tokens": existing["max_new_tokens"]}),
    ])

    assert _data_write_calls(conn) == [], \
        "An unchanged (duplicate) group must not be written."


@pytest.mark.asyncio
async def test_store_arguments_isolates_instances_across_pipelines():
    """Two pipelines write with their own pipeline key (chatqna vs docsum)."""
    chatqna = make_controller(pipeline="chatqna")
    docsum = make_controller(pipeline="docsum")

    conn_a = make_conn()
    conn_a.fetchval = AsyncMock(return_value=0)
    attach_pool(chatqna, conn_a)

    conn_b = make_conn()
    conn_b.fetchval = AsyncMock(return_value=0)
    attach_pool(docsum, conn_b)

    await chatqna.store_arguments([ComponentArgument(name="llm", data={"max_new_tokens": 512})])
    await docsum.store_arguments([ComponentArgument(name="llm", data={"max_new_tokens": 999})])

    write_a = _data_write_calls(conn_a)[0]
    write_b = _data_write_calls(conn_b)[0]

    assert write_a.args[1] == "chatqna", "First controller must write its own pipeline key."
    assert write_b.args[1] == "docsum", "Second controller must write its own pipeline key."
    assert json.loads(write_a.args[5])["max_new_tokens"] == 512
    assert json.loads(write_b.args[5])["max_new_tokens"] == 999


@pytest.mark.asyncio
async def test_store_arguments_propagates_write_errors(controller):
    conn = make_conn()
    conn.fetchval = AsyncMock(return_value=0)
    conn.execute = AsyncMock(side_effect=RuntimeError("boom"))
    attach_pool(controller, conn)

    with pytest.raises(Exception, match="Failed to store document"):
        await controller.store_arguments([
            ComponentArgument(name="llm", data={"max_new_tokens": 512}),
        ])


@pytest.mark.asyncio
async def test_store_arguments_targets_supplied_pipeline_and_tenant(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    # A caller may target a scope other than the controller's own; the write
    # must land in the supplied (pipeline, tenant), not the configured default.
    await controller.store_arguments(
        [ComponentArgument(name="llm", data={"max_new_tokens": 512})],
        pipeline="chatqna",
        tenant="alice",
    )

    write = _data_write_calls(conn)[0]
    assert write.args[1] == "chatqna", "Supplied pipeline must override the controller's."
    assert write.args[2] == "alice", "Supplied tenant must override the controller's."
    # The existing-row read and version query must use the same target scope.
    read_call = conn.fetchrow.await_args_list[0]
    assert read_call.args[1] == "chatqna"
    assert read_call.args[2] == "alice"


@pytest.mark.asyncio
async def test_store_arguments_defaults_to_controller_scope(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    await controller.store_arguments(
        [ComponentArgument(name="llm", data={"max_new_tokens": 512})])

    write = _data_write_calls(conn)[0]
    assert write.args[1] == controller.pipeline, "Omitted pipeline must fall back to the default."
    assert write.args[2] == controller.tenant, "Omitted tenant must fall back to the default."


@pytest.mark.asyncio
async def test_store_arguments_rejects_empty_pipeline(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    # An explicit empty scope must be rejected, not silently treated as the
    # default, so a caller never gets false confidence a blank scope was used.
    with pytest.raises(ValueError, match="pipeline must be a non-empty string"):
        await controller.store_arguments(
            [ComponentArgument(name="llm", data={"max_new_tokens": 512})],
            pipeline="")

    assert _data_write_calls(conn) == [], \
        "An empty pipeline must be rejected before any write."


@pytest.mark.asyncio
async def test_store_arguments_rejects_empty_tenant(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="tenant must be a non-empty string"):
        await controller.store_arguments(
            [ComponentArgument(name="llm", data={"max_new_tokens": 512})],
            tenant="")

    assert _data_write_calls(conn) == [], \
        "An empty tenant must be rejected before any write."


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_tenant", ["user:alice", "a b", "acme/team", "café"])
async def test_store_arguments_rejects_tenant_outside_charset(controller, bad_tenant):
    conn = make_conn()
    attach_pool(controller, conn)

    # A tenant must stay usable as a downstream key, so a value outside
    # [A-Za-z0-9_-] is rejected at write time.
    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await controller.store_arguments(
            [ComponentArgument(name="llm", data={"max_new_tokens": 512})],
            tenant=bad_tenant)

    assert _data_write_calls(conn) == [], \
        "A tenant outside the allowed charset must be rejected before any write."


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_pipeline", ["chat:qa", "chat qa", "chat.qa", "chat*"])
async def test_store_arguments_rejects_pipeline_outside_charset(controller, bad_pipeline):
    conn = make_conn()
    attach_pool(controller, conn)

    # A pipeline becomes part of the downstream key as well, so a value the
    # broker cannot represent is rejected at write time.
    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await controller.store_arguments(
            [ComponentArgument(name="llm", data={"max_new_tokens": 512})],
            pipeline=bad_pipeline)

    assert _data_write_calls(conn) == [], \
        "A pipeline outside the allowed charset must be rejected before any write."


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["alice\n", "alice\nbob"])
async def test_store_arguments_rejects_tenant_with_newline(controller, value):
    conn = make_conn()
    attach_pool(controller, conn)

    # A trailing newline must not slip through the charset check.
    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await controller.store_arguments(
            [ComponentArgument(name="llm", data={"max_new_tokens": 512})],
            tenant=value)

    assert _data_write_calls(conn) == [], \
        "A tenant containing a newline must be rejected before any write."


@pytest.mark.asyncio
async def test_store_arguments_accepts_uuid_tenant(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    # A Keycloak sub is a UUID, which is within the allowed charset.
    uuid_tenant = "550e8400-e29b-41d4-a716-446655440000"
    await controller.store_arguments(
        [ComponentArgument(name="llm", data={"max_new_tokens": 512})],
        tenant=uuid_tenant)

    assert _data_write_calls(conn)[0].args[2] == uuid_tenant, \
        "A UUID tenant must be accepted and written."


@pytest.mark.asyncio
async def test_store_arguments_rejects_bad_default_tenant(make_conn=make_conn):
    # An env-derived default that contains KV-illegal characters must be
    # rejected even when the caller does not supply an explicit tenant, so
    # bad configuration never produces a silently-wrong write.
    bad_controller = make_controller(tenant="user:alice")
    conn = make_conn()
    attach_pool(bad_controller, conn)

    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await bad_controller.store_arguments(
            [ComponentArgument(name="llm", data={"max_new_tokens": 512})])

    assert _data_write_calls(conn) == [], \
        "A bad configured tenant default must be rejected before any write."


@pytest.mark.asyncio
async def test_store_arguments_rejects_bad_default_pipeline(make_conn=make_conn):
    # An env-derived default pipeline with KV-illegal characters is caught
    # before any write, even when the caller omits an explicit pipeline.
    bad_controller = make_controller(pipeline="chat:qa")
    conn = make_conn()
    attach_pool(bad_controller, conn)

    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await bad_controller.store_arguments(
            [ComponentArgument(name="llm", data={"max_new_tokens": 512})])

    assert _data_write_calls(conn) == [], \
        "A bad configured pipeline default must be rejected before any write."


# ---------------------------------------------------------------------------
# 3b. read_group (per-key read)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_group_returns_single_group_with_metadata(controller):
    conn = make_conn()
    stored = LLMParams().model_dump()
    conn.fetchrow = AsyncMock(return_value={
        "params_key": "llm_primary",
        "params_kind": "llm",
        "values": json.dumps(stored),
        "version": 7,
    })
    attach_pool(controller, conn)

    result = await controller.read_group("llm_primary")

    assert result["params_key"] == "llm_primary"
    assert result["params_kind"] == "llm"
    assert result["version"] == 7
    assert result["values"] == stored


@pytest.mark.asyncio
async def test_read_group_queries_composite_key(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value={
        "params_key": "llm", "params_kind": "llm",
        "values": json.dumps(LLMParams().model_dump()), "version": 1,
    })
    attach_pool(controller, conn)

    await controller.read_group("llm")

    call = conn.fetchrow.await_args_list[0]
    # Query is keyed on (pipeline, tenant, params_key).
    assert call.args[1] == controller.pipeline
    assert call.args[2] == controller.tenant
    assert call.args[3] == "llm"


@pytest.mark.asyncio
async def test_read_group_returns_none_when_missing(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    attach_pool(controller, conn)

    assert await controller.read_group("nope") is None


@pytest.mark.asyncio
async def test_read_group_queries_supplied_scope(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value={
        "params_key": "llm", "params_kind": "llm",
        "values": json.dumps(LLMParams().model_dump()), "version": 1,
    })
    attach_pool(controller, conn)

    # An explicit scope must be queried instead of the controller's default,
    # so a per-pipeline or per-tenant row is addressable.
    await controller.read_group("llm", pipeline="chatqna", tenant="alice")

    call = conn.fetchrow.await_args_list[0]
    assert call.args[1] == "chatqna", "Supplied pipeline must be queried."
    assert call.args[2] == "alice", "Supplied tenant must be queried."


@pytest.mark.asyncio
async def test_read_group_rejects_empty_pipeline(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="pipeline must be a non-empty string"):
        await controller.read_group("llm", pipeline="")

    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_group_rejects_tenant_outside_charset(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await controller.read_group("llm", tenant="user:alice")

    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_group_rejects_bad_default_tenant():
    # An env-derived default tenant with KV-illegal characters is caught on
    # every read, even when the caller does not supply an explicit tenant.
    bad_controller = make_controller(tenant="user:alice")
    conn = make_conn()
    attach_pool(bad_controller, conn)

    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await bad_controller.read_group("llm")

    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_group_rejects_bad_default_pipeline():
    # An env-derived default pipeline with KV-illegal characters is caught on
    # every read, even when the caller does not supply an explicit pipeline.
    bad_controller = make_controller(pipeline="chat:qa")
    conn = make_conn()
    attach_pool(bad_controller, conn)

    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await bad_controller.read_group("llm")

    conn.fetchrow.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. SCHEMA_DDL / constants
# ---------------------------------------------------------------------------

def test_schema_ddl_declares_table_and_primary_key():
    assert "CREATE TABLE IF NOT EXISTS fingerprint_config" in SCHEMA_DDL
    assert "PRIMARY KEY (pipeline, tenant, params_key)" in SCHEMA_DDL


def test_schema_ddl_declares_expected_columns():
    for column in ("params_kind", "schema_version", "version", "updated_at"):
        assert column in SCHEMA_DDL, f"DDL must declare the {column} column."
    assert "values         jsonb" in SCHEMA_DDL or "values" in SCHEMA_DDL, \
        "DDL must declare the values column."
    assert "jsonb" in SCHEMA_DDL, "values must be stored as jsonb."


def test_schema_ddl_wires_notify_trigger():
    assert "pg_notify" in SCHEMA_DDL, "DDL must emit a NOTIFY on change."
    assert NOTIFY_CHANNEL in SCHEMA_DDL, "DDL must notify on the declared channel."
    assert "CREATE TRIGGER fingerprint_config_notify" in SCHEMA_DDL
    assert "AFTER INSERT OR UPDATE ON fingerprint_config" in SCHEMA_DDL


def test_notify_channel_and_schema_version_constants():
    assert NOTIFY_CHANNEL == "fingerprint_config_changed"
    assert SCHEMA_VERSION == 1


def test_group_model_and_grouping_constants_are_consistent():
    assert set(GROUP_MODELS.keys()) == {"llm", "retriever", "reranker", "docsum"} | set(NESTED_GROUPS.keys()), \
        "GROUP_MODELS must cover every mergeable group (flat data groups + nested)."
    assert NESTED_GROUPS == {
        "query_rewrite": "query_rewrite_params",
        "input_guard": "input_guardrail_params",
        "output_guard": "output_guardrail_params",
        "dataprep_guard": "dataprep_guardrail_params",
    }


# ---------------------------------------------------------------------------
# 6. _default_values_for (per-kind defaults)
# ---------------------------------------------------------------------------

def test_default_values_for_matches_odm_defaults(controller):
    assert controller._default_values_for("llm") == LLMParams().model_dump()
    assert controller._default_values_for("retriever") == RetrieverParams().model_dump()
    assert controller._default_values_for("reranker") == RerankerParams().model_dump()
    assert controller._default_values_for("query_rewrite") == QueryRewriteParams().model_dump()
    assert controller._default_values_for("docsum") == DocsumParams().model_dump()


def test_default_values_for_docsum_matches_microservice_defaults(controller):
    docsum = controller._default_values_for("docsum")

    assert docsum["summary_type"] == "map_reduce", \
        "Default summary_type must match the docsum microservice default."
    assert docsum["max_new_tokens"] == 1024
    assert docsum["stream"] is True
    assert set(docsum.keys()) == {"summary_type", "max_new_tokens", "stream"}, \
        "docsum default must carry exactly the fields the microservice reads."


def test_default_values_for_guardrail_has_all_scanners_disabled(controller):
    input_guard = controller._default_values_for("input_guard")

    assert set(input_guard.keys()) == {
        "anonymize", "ban_substrings", "ban_topics", "code", "invisible_text",
        "prompt_injection", "regex", "secrets", "sentiment", "token_limit", "toxicity",
    }, "input_guard default must include every scanner."
    assert all(
        scanner["enabled"] is False for scanner in input_guard.values()
    ), "Every scanner must default to disabled."


def test_default_values_for_prompt_template_follows_language():
    en = make_controller(template_language="en")._default_values_for("prompt_template")
    pl = make_controller(template_language="pl")._default_values_for("prompt_template")

    assert "helpful, respectful, and honest assistant" in en["system_prompt_template"]
    assert "asystentem" in pl["system_prompt_template"]


def test_default_values_for_unknown_kind_raises(controller):
    with pytest.raises(ValueError, match="Unknown params_kind"):
        controller._default_values_for("not_a_kind")


# ---------------------------------------------------------------------------
# 7. ensure_keys
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ensure_keys_inserts_on_conflict_do_nothing(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    await controller.ensure_keys([{"params_key": "llm", "params_kind": "llm"}])

    batches = _seed_batch_calls(conn)
    assert len(batches) == 1, "ensure_keys must seed in a single batched round-trip."
    assert "ON CONFLICT (pipeline, tenant, params_key)" in batches[0].args[0]
    assert "DO NOTHING" in batches[0].args[0], \
        "ensure_keys must never overwrite an existing row."
    rows = _seed_rows(conn)
    assert len(rows) == 1, "ensure_keys must seed the requested key."
    # Row tuple: pipeline, tenant, params_key, params_kind, values_json, ...
    assert rows[0][2] == "llm", "params_key must be written."
    assert rows[0][3] == "llm", "params_kind must be written."
    assert json.loads(rows[0][4]) == LLMParams().model_dump(), \
        "Default values for the kind must be seeded."


@pytest.mark.asyncio
async def test_ensure_keys_is_idempotent_across_calls(controller):
    # A store where the row already exists: DO NOTHING affects no rows, so a
    # repeated call issues the same INSERT ... DO NOTHING without error.
    conn = make_conn()
    attach_pool(controller, conn)

    await controller.ensure_keys([{"params_key": "llm", "params_kind": "llm"}])
    await controller.ensure_keys([{"params_key": "llm", "params_kind": "llm"}])

    for call in _seed_batch_calls(conn):
        assert "DO NOTHING" in call.args[0], \
            "Repeated ensure_keys calls must stay no-op upserts."


@pytest.mark.asyncio
async def test_ensure_keys_two_same_kind_keys_are_independent(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    await controller.ensure_keys([
        {"params_key": "llm_answer", "params_kind": "llm"},
        {"params_key": "llm_rewrite", "params_kind": "llm"},
    ])

    rows = _seed_rows(conn)
    assert len(rows) == 2, "Each key must produce its own row."
    written_keys = {row[2] for row in rows}
    assert written_keys == {"llm_answer", "llm_rewrite"}, \
        "Two same-kind keys must be addressable under distinct params_key values."
    for row in rows:
        assert row[3] == "llm", "Both rows share the llm kind."
        assert json.loads(row[4]) == LLMParams().model_dump()


@pytest.mark.asyncio
async def test_ensure_keys_seeds_docsum_pipeline_keys(controller):
    # The docsum pipeline declares an llm step and a docsum step, so the
    # controller ensures both keys. docsum is flat, so its seeded value carries
    # its fields at the top level (not wrapped under a nested key).
    conn = make_conn()
    attach_pool(controller, conn)

    await controller.ensure_keys([
        {"params_key": "llm", "params_kind": "llm"},
        {"params_key": "docsum", "params_kind": "docsum"},
    ])

    rows = _seed_rows(conn)
    seeded = {row[2]: (row[3], json.loads(row[4])) for row in rows}
    assert set(seeded) == {"llm", "docsum"}, "Both docsum-pipeline keys must be seeded."
    assert seeded["docsum"][0] == "docsum", "docsum key must carry the docsum kind."
    assert seeded["docsum"][1] == DocsumParams().model_dump(), \
        "docsum default must be seeded in flat wire shape."


@pytest.mark.asyncio
async def test_ensure_keys_seeds_at_current_version(controller):
    conn = make_conn()
    conn.fetchval = AsyncMock(return_value=5)  # existing rows already at v5
    attach_pool(controller, conn)

    await controller.ensure_keys([{"params_key": "retriever", "params_kind": "retriever"}])

    row = _seed_rows(conn)[0]
    assert row[5] == SCHEMA_VERSION, "schema_version must be written."
    assert row[6] == 6, \
        "Seeded key must use the current next version to keep versions monotonic."


@pytest.mark.asyncio
async def test_ensure_keys_targets_supplied_pipeline_and_tenant(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    await controller.ensure_keys(
        [{"params_key": "llm", "params_kind": "llm"}],
        pipeline="docsum",
        tenant="acme",
    )

    row = _seed_rows(conn)[0]
    assert row[0] == "docsum", "Supplied pipeline must override the controller's."
    assert row[1] == "acme", "Supplied tenant must override the controller's."


@pytest.mark.asyncio
async def test_ensure_keys_rejects_unknown_kind(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="Unknown params_kind"):
        await controller.ensure_keys([{"params_key": "x", "params_kind": "bogus"}])

    assert _seed_rows(conn) == [], \
        "An unknown kind must be rejected before any write."


@pytest.mark.asyncio
async def test_ensure_keys_rejects_missing_fields(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="params_key and params_kind"):
        await controller.ensure_keys([{"params_key": "llm"}])


@pytest.mark.asyncio
async def test_ensure_keys_rejects_non_list_keys(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="keys must be a list"):
        await controller.ensure_keys({"params_key": "llm", "params_kind": "llm"})


@pytest.mark.asyncio
async def test_ensure_keys_rejects_non_dict_item(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="must be a .* object"):
        await controller.ensure_keys(["llm"])


@pytest.mark.asyncio
async def test_ensure_keys_rejects_non_string_fields(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="string params_key"):
        await controller.ensure_keys([{"params_key": 123, "params_kind": "llm"}])

    assert _seed_rows(conn) == [], \
        "A non-string params_key must be rejected before any write."


@pytest.mark.asyncio
async def test_ensure_keys_rejects_non_string_pipeline(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match="pipeline must be a non-empty string"):
        await controller.ensure_keys(
            [{"params_key": "llm", "params_kind": "llm"}], pipeline=123)

    assert _seed_rows(conn) == [], \
        "A non-string pipeline must be rejected before any write."


@pytest.mark.asyncio
async def test_ensure_keys_rejects_tenant_outside_charset(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_-\]"):
        await controller.ensure_keys(
            [{"params_key": "llm", "params_kind": "llm"}], tenant="user:alice")

    assert _seed_rows(conn) == [], \
        "A tenant outside the allowed charset must be rejected before any write."


@pytest.mark.parametrize("bad_key", ["llm.primary", "llm primary", "llm*", "llm>", "llm."])
@pytest.mark.asyncio
async def test_ensure_keys_rejects_params_key_outside_charset(controller, bad_key):
    conn = make_conn()
    attach_pool(controller, conn)

    # A params_key carrying a dot, whitespace or a subject wildcard would be
    # dropped by the KV projection, so it is rejected at write time instead.
    with pytest.raises(ValueError, match=r"\[A-Za-z0-9_/=-\]"):
        await controller.ensure_keys(
            [{"params_key": bad_key, "params_kind": "llm"}])

    assert _seed_rows(conn) == [], \
        "A params_key outside the allowed charset must be rejected before any write."


@pytest.mark.asyncio
async def test_ensure_keys_accepts_valid_params_key(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    # An alnum/underscore key is a legal KV segment and is seeded normally.
    await controller.ensure_keys(
        [{"params_key": "llm_primary", "params_kind": "llm"}])

    rows = _seed_rows(conn)
    assert len(rows) == 1, "A valid params_key must be seeded."
    assert rows[0][2] == "llm_primary"


@pytest.mark.asyncio
async def test_ensure_keys_propagates_write_errors(controller):
    conn = make_conn()
    conn.executemany = AsyncMock(side_effect=RuntimeError("boom"))
    attach_pool(controller, conn)

    with pytest.raises(Exception, match="Failed to ensure keys"):
        await controller.ensure_keys([{"params_key": "llm", "params_kind": "llm"}])


# ---------------------------------------------------------------------------
# 8. tolerant read
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_group_tolerates_unknown_stored_fields(controller):
    # A row written by a newer/older revision carries a field this build does
    # not know. The read path must pass it through instead of crashing.
    conn = make_conn()
    stored = LLMParams().model_dump()
    stored["future_field"] = "surprise"
    conn.fetchrow = AsyncMock(return_value={
        "params_key": "llm", "params_kind": "llm",
        "values": json.dumps(stored), "version": 1,
    })
    attach_pool(controller, conn)

    values = (await controller.read_group("llm"))["values"]

    assert values["future_field"] == "surprise", \
        "Unknown stored fields must not break the read path."
    assert values["max_new_tokens"] == 1024, "Known fields still read as usual."


# ---------------------------------------------------------------------------
# 9. wire shape (to_wire_shape / from_wire_shape)
# ---------------------------------------------------------------------------

def test_to_wire_shape_leaves_flat_kinds_bare():
    values = LLMParams().model_dump()
    # A kind is flat when it is not registered as nested, so derive the set
    # under test rather than hardcoding it.
    flat_kinds = VALID_GROUPS - set(NESTED_GROUPS)
    assert flat_kinds, "There must be at least one flat kind to exercise."
    for kind in flat_kinds:
        assert to_wire_shape(kind, values) == values, \
            f"A flat kind ({kind}) must keep its fields at the top level."


def test_to_wire_shape_wraps_nested_kinds_under_their_key():
    values = {"anonymize": {"enabled": True}}
    for kind, out_key in NESTED_GROUPS.items():
        shaped = to_wire_shape(kind, values)
        assert shaped == {out_key: values}, \
            f"A nested kind ({kind}) must be wrapped under {out_key}."


def test_wire_shape_round_trips_for_every_kind():
    # Every writable kind must survive shape -> unwrap unchanged, so what is
    # stored and served can be recovered to the bare values the model expects.
    values = {"some_field": 1, "nested": {"a": True}}
    for kind in VALID_GROUPS:
        assert from_wire_shape(kind, to_wire_shape(kind, values)) == values, \
            f"Wire shape must round-trip for kind {kind}."


def test_from_wire_shape_tolerates_bare_nested_value():
    # A nested row written before values were shaped on write still carries the
    # bare values; the read path must return them unchanged (no migration).
    bare = {"anonymize": {"enabled": True}}
    assert from_wire_shape("input_guard", bare) == bare, \
        "A pre-shape bare nested value must be read unchanged."


def test_wire_shape_is_derived_only_from_nested_groups():
    # The flat-vs-nested decision must come solely from NESTED_GROUPS, so a
    # hypothetical new nested kind is shaped without any other code change.
    hypothetical_kind = "reasoning_guard"
    hypothetical_out_key = "reasoning_guardrail_params"
    assert hypothetical_kind not in NESTED_GROUPS
    # Not registered yet: treated as flat (no wrapping).
    assert to_wire_shape(hypothetical_kind, {"x": 1}) == {"x": 1}
    # Registering it in the single source is all it takes to nest it.
    monkey = dict(NESTED_GROUPS)
    monkey[hypothetical_kind] = hypothetical_out_key
    import comps.system_fingerprint.utils.erag_system_fingerprint as mod
    original = mod.NESTED_GROUPS
    mod.NESTED_GROUPS = monkey
    try:
        assert to_wire_shape(hypothetical_kind, {"x": 1}) == {hypothetical_out_key: {"x": 1}}
    finally:
        mod.NESTED_GROUPS = original


@pytest.mark.asyncio
async def test_store_arguments_stores_nested_kind_in_wire_shape(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="input_guard", data={"anonymize": {"enabled": True}}),
    ])

    writes = _data_write_calls(conn)
    assert len(writes) == 1
    stored = json.loads(writes[0].args[5])
    # The persisted value is already wire-shaped: wrapped under its dedicated
    # key so the fragment can be merged downstream without shape knowledge.
    assert "input_guardrail_params" in stored, \
        "A nested kind must be stored wrapped under its wire key."
    assert stored["input_guardrail_params"]["anonymize"]["enabled"] is True


@pytest.mark.asyncio
async def test_store_arguments_stores_flat_kind_bare(controller):
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=0)
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="llm", data={"max_new_tokens": 512}),
    ])

    stored = json.loads(_data_write_calls(conn)[0].args[5])
    assert stored["max_new_tokens"] == 512, "A flat kind must be stored with bare fields."
    assert "llm" not in stored, "A flat kind must not be wrapped under a key."


@pytest.mark.asyncio
async def test_store_arguments_merges_nested_kind_against_unwrapped_existing(controller):
    conn = make_conn()
    # Existing row is stored wire-shaped (wrapped under its dedicated key).
    existing_bare = {"anonymize": {"enabled": False}, "toxicity": {"enabled": True}}
    conn.fetchrow = AsyncMock(return_value={
        "values": json.dumps({"input_guardrail_params": existing_bare}),
        "params_kind": "input_guard",
    })
    conn.fetchval = AsyncMock(return_value=2)
    attach_pool(controller, conn)

    await controller.store_arguments([
        ComponentArgument(name="input_guard", data={"anonymize": {"enabled": True}}),
    ])

    stored = json.loads(_data_write_calls(conn)[0].args[5])
    merged = stored["input_guardrail_params"]
    assert merged["anonymize"]["enabled"] is True, "Patched scanner must be updated."
    assert merged["toxicity"]["enabled"] is True, \
        "Sibling scanner must be preserved through the unwrap/merge/rewrap."


@pytest.mark.asyncio
async def test_ensure_keys_seeds_nested_kind_in_wire_shape(controller):
    conn = make_conn()
    attach_pool(controller, conn)

    await controller.ensure_keys([{"params_key": "input_guard", "params_kind": "input_guard"}])

    seeded = json.loads(_seed_rows(conn)[0][4])
    assert "input_guardrail_params" in seeded, \
        "A seeded nested kind must be stored in wire shape."


@pytest.mark.asyncio
async def test_read_group_unwraps_nested_kind_to_bare_values(controller):
    conn = make_conn()
    bare = {"anonymize": {"enabled": True}}
    conn.fetchrow = AsyncMock(return_value={
        "values": json.dumps({"input_guardrail_params": bare}),
        "params_kind": "input_guard",
    })
    attach_pool(controller, conn)

    # The write-path read must recover the bare group so merge/validation see
    # the plain scanner fields.
    row = await controller._read_group(conn, "input_guard")
    assert row["values"] == bare


# ---------------------------------------------------------------------------
# 10. _validate (DB-backed health)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_runs_select_one_when_reachable(controller):
    conn = make_conn()
    conn.fetchval = AsyncMock(return_value=1)
    attach_pool(controller, conn)

    await controller._validate()

    conn.fetchval.assert_awaited_once_with("SELECT 1")


@pytest.mark.asyncio
async def test_validate_raises_when_pool_not_initialized(controller):
    # The pool is opened at startup; a validate before it exists must fail so
    # the health check reports the backend as unavailable rather than up.
    controller.pool = None

    with pytest.raises(Exception, match="not initialized"):
        await controller._validate()


@pytest.mark.asyncio
async def test_validate_raises_on_query_error(controller):
    conn = make_conn()
    conn.fetchval = AsyncMock(side_effect=RuntimeError("db down"))
    attach_pool(controller, conn)

    # An unreachable database surfaces as a raised error, which the framework
    # health check turns into a non-200 response.
    with pytest.raises(Exception, match="Problem connecting to database cluster"):
        await controller._validate()


@pytest.mark.asyncio
async def test_validate_fails_fast_on_stalled_query(controller, monkeypatch):
    # A hung query must not block the health handler; the bounded timeout turns
    # a stall into a raised error instead.
    async def never_returns(_sql):
        await asyncio.sleep(3600)

    conn = make_conn()
    conn.fetchval = never_returns
    attach_pool(controller, conn)
    monkeypatch.setattr(
        "comps.system_fingerprint.utils.erag_system_fingerprint.VALIDATE_TIMEOUT_SECONDS",
        0.01)

    with pytest.raises(Exception, match="Problem connecting to database cluster"):
        await controller._validate()


# ---------------------------------------------------------------------------
# 11. params-kind catalog
# ---------------------------------------------------------------------------

def test_params_kind_catalog_returns_valid_groups():
    catalog = params_kind_catalog()

    assert set(catalog["kinds"]) == set(VALID_GROUPS), \
        "The catalog must expose exactly the write-path VALID_GROUPS."
    assert catalog["kinds"] == sorted(catalog["kinds"]), \
        "The catalog must be sorted for a stable response."


def test_params_kind_catalog_tracks_the_single_source():
    # The catalog must be derived from VALID_GROUPS, not a second hardcoded
    # list, so adding a kind there is the only change needed to publish it.
    assert params_kind_catalog()["kinds"] == sorted(VALID_GROUPS)


# ---------------------------------------------------------------------------
# 12. guard scope maps mirrored by the e2e helper
# ---------------------------------------------------------------------------

def test_guard_scope_maps_match_the_service():
    # The guard e2e helper restates GROUP_MODELS and NESTED_GROUPS for the three
    # guard scopes, because importing this module would pull the database driver
    # into the offline unit env. Renaming a group or its nested key here without
    # updating the helper would make the helper write a config the service never
    # reads, so the copies are pinned to the originals.
    from tests.e2e.helpers.guard_helper import (
        GUARD_PARAMS_MODELS,
        GUARD_READ_FIELDS,
        GuardType,
    )

    for guard_type in GuardType:
        assert GUARD_PARAMS_MODELS[guard_type] is GROUP_MODELS[guard_type.value], \
            f"guard_helper's value model for '{guard_type.value}' is not the service's."
        assert GUARD_READ_FIELDS[guard_type] == NESTED_GROUPS[guard_type.value], \
            f"guard_helper's read field for '{guard_type.value}' is not the service's."
