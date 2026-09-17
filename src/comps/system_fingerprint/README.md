# System Fingerprint Microservice

The System Fingerprint microservice is responsible for generating and managing unique fingerprints for different systems and giving user ability to store and update component arguments. It includes the necessary scripts, configurations, and utilities to efficiently handle fingerprint data stored in PostgreSQL.

## Table of Contents

1. [System Fingerprint Microservice](#system-fingerprint-microservice)
2. [Configuration Options](#configuration-options)
3. [Getting Started](#getting-started)
   - 3.1. [Prerequisites](#prerequisites)
   - 3.2. [🚀 Start System Fingerprint Microservice with Python (Option 1)](#-start-system-fingerprint-microservice-with-python-option-1)
     - 3.2.1. [Install Requirements](#install-requirements)
     - 3.2.2. [Start Microservice](#start-microservice)
   - 3.3. [🚀 Start System Fingerprint Microservice with Docker (Option 2)](#-start-system-fingerprint-microservice-with-docker-option-2)
     - 3.3.1. [Build the Docker service](#build-the-docker-service)
     - 3.3.2. [Run the Docker container](#run-the-docker-container)
   - 3.4. [Example API Requests](#example-api-requests)
     - 3.4.1. [Health Check](#health-check)
     - 3.4.2. [Change arguments](#change-arguments)
     - 3.4.3. [Read config](#read-config)
     - 3.4.4. [Read kinds](#read-kinds)
     - 3.4.5. [Ensure keys](#ensure-keys)
4. [Additional Information](#additional-information)
   - 4.1. [Project Structure](#project-structure)

## Configuration options

Configuration is done by specifying the PostgreSQL connection details and key dimensions. Optionally, you can specify the microservice's port.

| Environment Variable    | Default Value     | Description |
|-------------------------|-------------------|-------------|
| `SYSTEM_FINGERPRINT_POSTGRES_HOST` | `127.0.0.1` | PostgreSQL host |
| `SYSTEM_FINGERPRINT_POSTGRES_PORT` | `5432` | PostgreSQL port |
| `SYSTEM_FINGERPRINT_DATABASE_NAME` | `system_fingerprint` | Database name |
| `SYSTEM_FINGERPRINT_POSTGRES_USER` | `postgres` | Database user |
| `SYSTEM_FINGERPRINT_POSTGRES_PASSWORD` | `postgres` | Database password. The `postgres` default is for local development only - override it in production deployments. |
| `SYSTEM_FINGERPRINT_PIPELINE` | `default` | Pipeline key dimension |
| `SYSTEM_FINGERPRINT_TENANT` | `_global` | Tenant key dimension |
| `SYSTEM_FINGERPRINT_TEMPLATE_LANGUAGE` | `en` | The language of the default prompt template. Only `en` and `pl` are supported. |
| `SYSTEM_FINGERPRINT_USVC_PORT` | `6012` | (Optional) Microservice port |

### Data model

The microservice uses a single PostgreSQL table `fingerprint_config` with a composite primary key `(pipeline, tenant, params_key)`. Each row stores one parameter group:

- **`pipeline`** (text) - pipeline key dimension (e.g., `default`)
- **`tenant`** (text) - tenant key dimension (e.g., `_global`)
- **`params_key`** (text) - identifies the parameter group (e.g., `llm`, `retriever`, `reranker`, `query_rewrite`, `docsum`, `prompt_template`, `input_guard`, `output_guard`, `dataprep_guard`)
- **`params_kind`** (text) - parameter group category (same as `params_key` for most groups)
- **`values`** (jsonb) - the parameter payload, stored in its final wire shape (see [Wire shape](#wire-shape))
- **`schema_version`** (int) - schema version for the parameter shape
- **`version`** (bigint) - monotonic version per `(pipeline, tenant)` for ordering and optimistic locking
- **`updated_at`** (timestamptz) - last update timestamp

The table also has a trigger that sends a PostgreSQL `NOTIFY` on channel `fingerprint_config_changed` whenever a row is inserted or updated (the microservice only ever inserts and updates rows, never deletes them). The notification payload contains `pipeline/tenant/params_key`. This change-notification mechanism is consumed by the GMC controller, not by this microservice.

#### Scope

Every read and write addresses a `(pipeline, tenant)` scope. `SYSTEM_FINGERPRINT_PIPELINE` and `SYSTEM_FINGERPRINT_TENANT` set the default scope, and the seeding done at startup uses it. The full group set is seeded under that default scope; in addition, the dataprep guardrail group (`dataprep_guard`) is seeded under the `(dataprep, _global)` scope, so the dataprep worker finds its row present on first read. The `change_arguments` and `config` endpoints also take optional `pipeline`/`tenant` query parameters so a caller can target a scope other than the default - for example the `pipeline` a router serves (`chatqna`), so a parameter edit reaches the running pipeline instead of a scope no router reads. A router reads the scope matching its own `PIPELINE_NAME`, so a write and the router that consumes it must name the same pipeline.

### Wire shape

Each row's `values` payload is stored in its final wire shape - the exact fragment a consumer merges into the parameter set. A flat kind (`llm`, `retriever`, `reranker`, `docsum`, `prompt_template`) carries its fields at the top level; a nested kind (`query_rewrite`, `input_guard`, `output_guard`, `dataprep_guard`) carries its values wrapped under its dedicated key (`query_rewrite_params`, `input_guardrail_params`, `output_guardrail_params`, `dataprep_guardrail_params`). Because the value already carries its shape, a per-key read can be merged downstream without the reader knowing whether a kind is flat or nested. The flat-vs-nested mapping is defined once (in `utils/erag_system_fingerprint.py`), so adding a new group only touches this microservice. A row written before values were shaped is read back unchanged, so the shape can be adopted without a migration.

## Getting started
### Prerequisites

To run this microservice, a PostgreSQL database should already be running. The microservice automatically creates its schema on startup (a `fingerprint_config` table and a change-notification trigger). To run the database, you can use [the sample docker-compose file](./impl/database/postgres/docker-compose.yaml).

There're 2 ways to run this microservice:
  - [via Python](#-start-system-fingerprint-microservice-with-python-option-1)
  - [via Docker](#-start-system-fingerprint-microservice-with-docker-option-2) **(recommended)**

### 🚀 Start System Fingerprint Microservice with Python (Option 1)

#### Install Requirements
To freeze the dependencies of a particular microservice,[uv](https://github.com/astral-sh/uv) project manager is utilized. So before installing the dependencies, installing uv is required.
Next, use `uv sync` to install the dependencies. This command will create a virtual environment.

```bash
pip install uv
uv sync --locked --no-cache --project impl/microservice/pyproject.toml
source impl/microservice/.venv/bin/activate
```

#### Start Microservice

```bash
python system_fingerprint_microservice.py
```

### 🚀 Start System Fingerprint Microservice with Docker (Option 2)

Using a container is the preferred way to run the microservice.

#### Build the Docker service

Navigate to the `src` directory and use the Docker build command to create the image:

```bash
cd ../.. # src/ directory
docker build -t systemfingerprint_usvc:latest -f comps/system_fingerprint/impl/microservice/Dockerfile .
```

#### Run the Docker container

Remember, you can pass configuration variables by using the `-e` option with the Docker run command, such as the vector database configuration and database endpoint.

```bash
docker run -d --name=systemfingerprint-microservice --env-file comps/system_fingerprint/impl/microservice/.env --network=host systemfingerprint_usvc:latest
```
### Example API Requests

Once the System Fingerprint service is up and running, users can access the database using the following API endpoint. Each API serves a different purpose and returns an appropriate response. The System Fingerprint microservice accepts JSON as input and returns JSON.

#### Health Check

To perform a health check, use the following command:

```bash
curl http://localhost:6012/v1/health_check  \
  -X GET                                    \
  -H 'Content-Type: application/json'
```

`/v1/health_check` validates that PostgreSQL is reachable: a validate method registered with the microservice pings the database with a cheap `SELECT 1`. This is the same mechanism the other microservices use to report their backend, so the Kubernetes probes need no dedicated path. To bound the cost of a database round-trip per probe, the framework runs the validation at most once every 10 minutes (`TIMEFRAME_FOR_CHECKS`): when it runs and PostgreSQL is unreachable the request fails with a non-200; calls within the throttle window skip the check and return 200. Both the liveness and readiness probes point at this endpoint.

#### Change arguments

This endpoint allows you to change arguments and store them in PostgreSQL. It accepts input in the following format:

```python
List[ComponentArgument]
```

Where `ComponentArgument` is defined as:

```python
class ComponentArgument(BaseDoc):
    name: str
    data: dict
    params_kind: Optional[str] = None
```

Example curl command:

```bash
curl -X POST http://localhost:6012/v1/system_fingerprint/change_arguments \
-H "Content-Type: application/json" \
-d '[
    {
        "name": "llm",
        "data": {
            "max_new_tokens": 1024,
            "top_k": 10
        }
    }
]'
```

A full set of possible configurations can be found in the file [object_document_mapper.py](utils/object_document_mapper.py).

The `change_arguments` handler stores each item under its own `(pipeline, tenant, params_key)` row, where `name` is the `params_key`. It applies a field-level merge so that changing one field never resets its siblings.

The `params_key` is free-form, so two instances of the same kind (for example two LLM steps addressed as `llm_primary` and `llm_secondary`) can hold independent values. The value model is selected by the item's kind, resolved in order from the optional `params_kind` field, then the kind the key was already stored with, then the key itself when it is a canonical group name. A key with no resolvable kind is ignored, and an explicit `params_kind` outside the catalog returns a 400.

```bash
curl -X POST http://localhost:6012/v1/system_fingerprint/change_arguments \
-H "Content-Type: application/json" \
-d '[
    {"name": "llm_primary", "params_kind": "llm", "data": {"max_new_tokens": 1024}},
    {"name": "llm_secondary", "params_kind": "llm", "data": {"max_new_tokens": 512}}
]'
```

The write targets the `(pipeline, tenant)` scope given by the optional `pipeline` and `tenant` query parameters, falling back to the microservice's configured `SYSTEM_FINGERPRINT_PIPELINE` and `SYSTEM_FINGERPRINT_TENANT` when they are omitted. This lets a caller edit the scope a router actually reads (for example `pipeline=chatqna`) instead of only the microservice's own default. An explicit value that is empty is rejected with a 400 rather than silently falling back, so a caller never gets false confidence that a blank scope hit its default. Both `pipeline` and `tenant` may only contain characters in `[A-Za-z0-9_-]` so they stay usable as a downstream key; a value such as `user:alice` is rejected with a 400. Per-user identity is expected to come from a gateway-verified JWT `sub` (a UUID, which passes this check) rather than a caller-supplied value; that wiring is not in place yet.

```bash
curl -X POST "http://localhost:6012/v1/system_fingerprint/change_arguments?pipeline=chatqna" \
-H "Content-Type: application/json" \
-d '[
    {"name": "llm", "data": {"max_new_tokens": 512}}
]'
```

#### Read config

This endpoint returns a single stored group for a `(pipeline, tenant, params_key)`, keyed by the `params_key` query parameter. The optional `pipeline` and `tenant` query parameters select the scope, falling back to the microservice's configured `SYSTEM_FINGERPRINT_PIPELINE` and `SYSTEM_FINGERPRINT_TENANT` when omitted; an explicit empty value, or a `pipeline`/`tenant` outside `[A-Za-z0-9_-]`, returns a 400. The response carries the stored `values` together with the group's `params_kind` and monotonic `version`. The `values` are in their final [wire shape](#wire-shape) (a nested kind's values are wrapped under its dedicated key), so the fragment can be merged into the parameter set as-is. It returns a 404 when the key has no row.

```bash
curl "http://localhost:6012/v1/system_fingerprint/config?params_key=llm_primary&pipeline=chatqna"
```

#### Read kinds

This endpoint returns the catalog of parameter kinds the write path accepts, so a consumer can validate a `params_kind` against the owner instead of keeping its own copy. The list is derived from the same source the write path validates against, so a new kind appears here as soon as it is added to this microservice.

```bash
curl "http://localhost:6012/v1/system_fingerprint/kinds"
```

```json
{
    "kinds": [
        "dataprep_guard", "docsum", "input_guard", "llm", "output_guard",
        "prompt_template", "query_rewrite", "reranker", "retriever"
    ]
}
```

#### Ensure keys

This endpoint seeds default rows for a set of parameter keys without overwriting anything that already exists. Each key that is missing is inserted with the default values for its kind; keys that are already present are left untouched, so the call is idempotent and safe to repeat. It accepts a JSON body:

```json
{
    "pipeline": "default",
    "tenant": "_global",
    "keys": [
        {"params_key": "llm", "params_kind": "llm"},
        {"params_key": "retriever", "params_kind": "retriever"}
    ]
}
```

`pipeline` and `tenant` are optional and, when provided, must be non-empty strings; they fall back to the microservice's configured `SYSTEM_FINGERPRINT_PIPELINE` and `SYSTEM_FINGERPRINT_TENANT`. Each `params_key`/`params_kind` must be a non-empty string, and `params_kind` must be one of `llm`, `retriever`, `reranker`, `query_rewrite`, `docsum`, `prompt_template`, `input_guard`, `output_guard`, `dataprep_guard`; the default value payload is derived from that kind. Because `params_key` and `params_kind` are separate, two keys of the same kind (for example two `llm` groups) can be seeded under distinct keys and addressed independently. All keys in one request are seeded in a single batched write.

Example curl command:

```bash
curl -X POST http://localhost:6012/v1/system_fingerprint/ensure_keys \
-H "Content-Type: application/json" \
-d '{
    "keys": [
        {"params_key": "llm", "params_kind": "llm"}
    ]
}'
```

## Additional Information

### Project Structure

The project is organized into several directories:

- `impl/`: This directory contains configuration files for the System Fingerprint service.
- `utils/`: This directory contains scripts that are used by the System Fingerprint Microservice.
