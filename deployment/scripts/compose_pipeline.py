#!/usr/bin/env python3
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Pipeline composer - builds GMConnector CRD from base flow + variants.

Usage:
  compose_pipeline.py <pipeline_dir> <enabled_variants_csv> <template_vars_json>

Example:
  compose_pipeline.py pipelines/chatqna "query-rewrite" '{"endpoints": {...}}'

The variants argument is a CSV, but exactly one variant is supported: composition order
between several variants is undefined (see main()). Empty means base flow only.

Each step template (steps/<id>.yaml.j2, variants/<name>/steps.yaml.j2) is a unified
file holding BOTH the GMC step definition AND its recommended resources:

  step:                      # single GMC step (base step file)
    name: Llm
    ...
  resources:                 # recommended chart resources, keyed by <usvc>
    llm-usvc:
      replicas: 2
      resources: {...}
      # hpa: {...}           # when applicable

Variant step files may instead emit `steps:` (a list) plus optional `__nodes__:`
(extra GMC nodes) alongside their `resources:`.

Resources are aggregated ONLY for steps in the active flow (base + selected variants)
and written to the path given in template_vars['resources_output']; unselected variant
services are omitted entirely. The GMConnector CRD is written to stdout.
"""

import json
import sys
import yaml
from pathlib import Path
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import FileSystemLoader, TemplateNotFound, Undefined


class _MissingValueError(ValueError):
    """Raised by the `required` Jinja filter when a template value is absent."""


def _required(value, message):
    """Jinja filter: fail composition with a clear message if `value` is undefined/None.

    Used by shared step templates (e.g. _shared/steps/llm.yaml.j2) to fail closed with an
    actionable error instead of a cryptic 'dict object has no attribute ...'.
    """
    if value is None or isinstance(value, Undefined):
        raise _MissingValueError(message)
    return value


def _consume_rendered(rendered, rendered_steps, all_nodes, services):
    """Merge one rendered step/variant document into the accumulators.

    Handles the unified step-file format:
      - `step`      : a single GMC step mapping        -> appended to rendered_steps
      - `steps`     : a list of GMC step mappings       -> extended into rendered_steps
      - `__nodes__` : extra GMC nodes (nested routers)  -> merged into all_nodes
      - `resources` : recommended chart resources map   -> merged into services

    Naming convention (hand-maintained, verify against the GMC chart's `services.<usvc>`):
    a step's `internalService.serviceName` is the GMC-deployed Service name (`<name>-svc`,
    e.g. `llm-svc`), while its `resources` keys are the chart microservice keys
    (`<name>-usvc`, e.g. `llm-usvc`). The two are NOT mechanically derivable from each
    other (`input-scan-svc`->`in-guard-usvc`, `prompt-template-svc`->`prompt-template-usvc`); a wrong
    `<usvc>` key silently drops resource limits, so keys are declared explicitly.
    """
    if not isinstance(rendered, dict):
        raise ValueError(
            "Step template must render a mapping with 'step' or 'steps' keys, "
            f"got: {type(rendered).__name__}"
        )

    if '__nodes__' in rendered:
        all_nodes.update(rendered['__nodes__'])

    if 'resources' in rendered and rendered['resources']:
        # Fail loudly on colliding resource keys - silent last-wins could hide a typo
        # or an unintended override and feed Helm the wrong sizing.
        collisions = set(rendered['resources']) & set(services)
        if collisions:
            raise ValueError(
                f"Duplicate resource key(s) across step files: {sorted(collisions)}. "
                "Each <usvc> resources key must be declared by exactly one active step."
            )
        services.update(rendered['resources'])

    if 'steps' in rendered:
        rendered_steps.extend(rendered['steps'])
    elif 'step' in rendered:
        rendered_steps.append(rendered['step'])
    else:
        raise ValueError("Step template must define either 'step' or 'steps'")


def compose_pipeline(pipeline_dir, enabled_variants, template_vars):
    """
    Compose a GMConnector from base flow + variants using metadata.

    Args:
        pipeline_dir: Path to pipeline directory
        enabled_variants: List of variant names to enable
        template_vars: Dict of variables for Jinja2 templates

    Returns:
        Tuple of (GMConnector dict, aggregated resources dict).
    """
    pipeline_dir = Path(pipeline_dir)

    if not pipeline_dir.exists():
        raise FileNotFoundError(f"Pipeline directory not found: {pipeline_dir}")

    # Shared steps live one level up in `_shared/` (leading underscore so init flavour
    # discovery skips it). Pipeline-local step files take precedence over shared ones.
    shared_dir = pipeline_dir.parent / '_shared'

    # Control keys steer the composer, not the templates - pull them out first.
    pipeline_type = template_vars.pop('pipeline_type', pipeline_dir.name)
    pipeline_variant = template_vars.pop('pipeline_variant', 'base')
    template_vars.pop('resources_output', None)

    # 1. Load pipeline metadata
    pipeline_meta_path = pipeline_dir / 'pipeline.yaml'
    if not pipeline_meta_path.exists():
        raise FileNotFoundError(f"Pipeline metadata not found: {pipeline_meta_path}")

    with open(pipeline_meta_path) as f:
        pipeline_meta = yaml.safe_load(f)

    # 2. Load base flow (embedded in pipeline.yaml)
    if isinstance(pipeline_meta.get('base_flow'), list):
        steps = pipeline_meta['base_flow'].copy()
    else:
        raise ValueError("pipeline.yaml must define 'base_flow' as an ordered list of step ids")

    # 3. Apply variants using insert_after / insert_before / replaces
    for variant_name in enabled_variants:
        variant_dir = pipeline_dir / 'variants' / variant_name

        if not variant_dir.exists():
            raise FileNotFoundError(f"Variant directory not found: {variant_dir}")

        # Load variant metadata
        meta_path = variant_dir / 'meta.yaml'
        if not meta_path.exists():
            raise FileNotFoundError(f"Variant metadata not found: {meta_path}")

        with open(meta_path) as f:
            variant_meta = yaml.safe_load(f)

        # Apply composition directive
        if 'insert_after' in variant_meta:
            anchor = variant_meta['insert_after']
            if anchor not in steps:
                raise ValueError(
                    f"Variant '{variant_name}' insert_after anchor '{anchor}' not found in base flow"
                )
            idx = steps.index(anchor)
            steps.insert(idx + 1, f"_variant_{variant_name}")

        elif 'insert_before' in variant_meta:
            anchor = variant_meta['insert_before']
            if anchor not in steps:
                raise ValueError(
                    f"Variant '{variant_name}' insert_before anchor '{anchor}' not found in base flow"
                )
            steps.insert(steps.index(anchor), f"_variant_{variant_name}")

        elif 'replaces' in variant_meta:
            replaced_steps = variant_meta['replaces']
            if not replaced_steps:
                raise ValueError(f"Variant '{variant_name}' replaces list is empty")

            # Find indices of all replaced steps
            try:
                indices = [steps.index(step) for step in replaced_steps]
            except ValueError as e:
                raise ValueError(
                    f"Variant '{variant_name}' replaces step not found in base flow: {e}"
                )

            # Validate contiguity - replaced steps must be adjacent
            if indices != list(range(min(indices), max(indices) + 1)):
                raise ValueError(
                    f"Variant '{variant_name}' replaces non-contiguous steps: {replaced_steps}. "
                    f"Steps must be adjacent in base flow. Found at indices: {indices}"
                )

            # Replace span with variant marker
            start_idx = min(indices)
            end_idx = max(indices)
            steps = steps[:start_idx] + [f"_variant_{variant_name}"] + steps[end_idx + 1:]

        else:
            raise ValueError(
                f"Variant '{variant_name}' must specify 'insert_after', 'insert_before' "
                "or 'replaces' in meta.yaml"
            )

    # 4. Render all steps using Jinja2 (sandboxed for security). The loader searches the
    #    pipeline dir first, then the shared dir, so pipeline-local files win.
    jinja_env = SandboxedEnvironment(
        loader=FileSystemLoader([str(pipeline_dir), str(shared_dir)])
    )
    jinja_env.filters['required'] = _required

    rendered_steps = []
    all_nodes = {}
    services = {}

    for step_id in steps:
        if step_id.startswith('_variant_'):
            variant_name = step_id.replace('_variant_', '')
            template_path = f'variants/{variant_name}/steps.yaml.j2'
        else:
            template_path = f'steps/{step_id}.yaml.j2'

        try:
            template = jinja_env.get_template(template_path)
        except TemplateNotFound as e:
            raise FileNotFoundError(
                f"Step template not found: {template_path} "
                f"(searched {pipeline_dir} and {shared_dir}): {e}"
            )

        rendered = yaml.safe_load(template.render(**template_vars))
        _consume_rendered(rendered, rendered_steps, all_nodes, services)

    # 5. Build final GMConnector
    gmconnector = {
        'apiVersion': 'gmc.erag.intel.com/v1alpha3',
        'kind': 'GMConnector',
        'metadata': {
            'name': pipeline_meta['name'],
            'namespace': pipeline_meta['namespace'],
            'labels': {
                'app.kubernetes.io/name': 'gmconnector',
                'app.kubernetes.io/managed-by': 'kustomize',
                'gmc/platform': 'xeon',
                'gmc/pipeline-type': pipeline_type,
                'gmc/variant': pipeline_variant
            }
        },
        'spec': {
            'routerConfig': {
                'name': pipeline_meta['router']['name'],
                'serviceName': pipeline_meta['router']['service_name']
            },
            'nodes': {
                'root': {
                    'routerType': pipeline_meta['router']['type'],
                    'steps': rendered_steps
                }
            }
        }
    }

    # Add variant nodes if any
    if all_nodes:
        gmconnector['spec']['nodes'].update(all_nodes)

    return gmconnector, {'services': services}


def main():
    """Main entry point."""
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    pipeline_dir = sys.argv[1]
    enabled_variants_csv = sys.argv[2]
    template_vars_json = sys.argv[3]

    # Parse arguments. Dedupe: the same variant twice would apply its directive twice,
    # failing with a duplicate-resource-key error that points at the step files rather than
    # at the repeated argument (or, for a variant with no `resources:`, emitting the step
    # twice and deferring rejection to the GMC webhook at apply time).
    enabled_variants = list(dict.fromkeys(
        v.strip() for v in enabled_variants_csv.split(',') if v.strip()
    ))

    # Exactly one variant is supported. Variants mutate the flow in place, one after
    # another, so with several the result depends on argument order: two sharing an
    # insert_after anchor end up reversed, insert_before keeps argument order, and
    # overlapping spans fail naming whichever variant applied second. Applying several
    # needs a defined order plus an overlap check first; until then fail here rather than
    # emit a flow nobody chose. The Ansible layer only ever passes one (app_pipeline
    # validates pipeline_variant against the variants/ directories), so this guards
    # direct CLI use.
    if len(enabled_variants) > 1:
        print(
            f"Error: multiple variants are not supported yet (got {enabled_variants}). "
            "Composition order between variants is undefined - pass a single variant.",
            file=sys.stderr
        )
        sys.exit(1)

    try:
        template_vars = json.loads(template_vars_json)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in template_vars argument: {e}", file=sys.stderr)
        sys.exit(1)

    resources_output = template_vars.get('resources_output')

    # Compose pipeline
    try:
        gmconnector, resources = compose_pipeline(pipeline_dir, enabled_variants, template_vars)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error composing pipeline: {e}", file=sys.stderr)
        sys.exit(1)

    # Write the aggregated resources values file (new output alongside the GMConnector).
    if resources_output:
        try:
            with open(resources_output, 'w') as f:
                yaml.dump(resources, f, default_flow_style=False, sort_keys=False, width=120)
        except OSError as e:
            print(f"Error writing resources output '{resources_output}': {e}", file=sys.stderr)
            sys.exit(1)

    # Output GMConnector YAML (preserve order, no sorting)
    print(yaml.dump(gmconnector, default_flow_style=False, sort_keys=False, width=120))


if __name__ == '__main__':
    main()
