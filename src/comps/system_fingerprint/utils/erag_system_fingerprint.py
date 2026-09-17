# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Type

import asyncpg
from pydantic import BaseModel

from comps.cores.mega.logger import get_erag_logger
from comps.system_fingerprint.utils.object_document_mapper import (
    AnonymizeModel,
    BanSubstringsModel,
    BanTopicsModel,
    BiasModel,
    CodeModel,
    DeanonymizeModel,
    DocsumParams,
    FactualConsistencyModel,
    InvisibleText,
    JSONModel,
    LLMGuardDataprepGuardrailParams,
    LLMGuardInputGuardrailParams,
    LLMGuardOutputGuardrailParams,
    LLMParams,
    MaliciousURLsModel,
    NoRefusalLightModel,
    NoRefusalModel,
    PromptInjectionModel,
    PromptTemplateEnParams,
    PromptTemplatePlParams,
    QueryRewriteParams,
    ReadingTimeModel,
    RegexModel,
    RelevanceModel,
    RerankerParams,
    RetrieverParams,
    SecretsModel,
    SensitiveModel,
    SentimentModel,
    TokenLimitModel,
    ToxicityModel,
    URLReachabilityModel,
)


logger = get_erag_logger(f"{__file__.split('comps/')[1].split('/', 1)[0]}_microservice")

# Current schema revision written by this service. The read path tolerates
# older values so that rolling updates during schema evolution stay safe.
SCHEMA_VERSION = 1

# Channel the database NOTIFY trigger emits on when a config row changes.
# Consumed by the GMC controller, which LISTENs on it.
NOTIFY_CHANNEL = "fingerprint_config_changed"

# Startup connection retry. A database that is still coming up should not turn
# into a crash loop, so the pool is retried a bounded number of times with a
# fixed delay before init gives up.
CONNECT_RETRIES = 240
CONNECT_RETRY_DELAY_SECONDS = 5.0

# Upper bound on the health validation query. The check runs from the shared
# health endpoint, so a stalled connection must fail fast instead of blocking
# the handler until the network timeout fires.
VALIDATE_TIMEOUT_SECONDS = 5.0

# Per-statement timeout for every pooled query, enforced by the asyncpg driver
# (command_timeout), not by Postgres statement_timeout. Each statement this
# service runs (single-row read, small seed insert, advisory-lock acquire) is
# sub-second, so a statement that runs long means a stuck backend. Bounding it
# lets asyncpg cancel the query and recycle the connection back to the pool
# instead of holding it forever: an unbounded read hangs the handler until the
# client gives up and, once every pooled connection is stuck the same way,
# starves the pool so every subsequent request hangs too.
STATEMENT_TIMEOUT_SECONDS = 30.0

# Groups that are nested under a dedicated key in the wire shape. Maps the
# stored ``params_key`` to the top-level key downstream services read; any group
# absent from this mapping keeps its fields at the top level.
NESTED_GROUPS = {
    "query_rewrite": "query_rewrite_params",
    "input_guard": "input_guardrail_params",
    "output_guard": "output_guardrail_params",
    "dataprep_guard": "dataprep_guardrail_params",
}

# Extra default rows seeded under a scope other than the controller's own. Each
# entry is a (pipeline, tenant, params_key) that a consumer reading a non-default
# scope needs present on first read. The dataprep pipeline reads only its
# guardrail group, so that is the single key seeded under (dataprep, _global).
EXTRA_SCOPED_SEEDS = (
    ("dataprep", "_global", "dataprep_guard"),
)

# Value-object model for each stored group, used to validate and normalise
# incoming data and to fill defaults for freshly created rows. The
# prompt_template entry is resolved at runtime because it depends on the
# configured template language.
GROUP_MODELS: Dict[str, Type[BaseModel]] = {
    "llm": LLMParams,
    "retriever": RetrieverParams,
    "reranker": RerankerParams,
    "query_rewrite": QueryRewriteParams,
    "docsum": DocsumParams,
    "input_guard": LLMGuardInputGuardrailParams,
    "output_guard": LLMGuardOutputGuardrailParams,
    "dataprep_guard": LLMGuardDataprepGuardrailParams,
}

# Every group name accepted on the write path. prompt_template is validated
# through a language-dependent model resolved at runtime, so it lives outside
# GROUP_MODELS but is still a first-class writable group.
VALID_GROUPS = frozenset(GROUP_MODELS) | {"prompt_template"}

# Groups whose default payload is just the model's own defaults. The guardrail
# groups are excluded because each is assembled from its per-scanner models, and
# prompt_template is excluded because it resolves through a language-dependent
# model at runtime. Models are taken from GROUP_MODELS so the class mapping stays
# defined in one place; only the kind list lives here.
_SIMPLE_DEFAULT_KINDS = ("llm", "retriever", "reranker", "query_rewrite", "docsum")
_SIMPLE_DEFAULT_MODELS: Dict[str, Type[BaseModel]] = {
    kind: GROUP_MODELS[kind] for kind in _SIMPLE_DEFAULT_KINDS
}

# Characters a scope dimension (pipeline, tenant) may contain. Both become part
# of the key a downstream broker projects the row under, so a value outside this
# set is rejected before it can produce a key the broker cannot represent. A
# Keycloak ``sub`` (a UUID) and a namespace-derived pipeline name pass; a value
# such as ``user:alice`` does not. ``fullmatch`` is used so a trailing newline
# (which ``$`` would tolerate) cannot slip through.
SCOPE_PATTERN = re.compile(r"[A-Za-z0-9_-]+")

# Characters a params_key may contain. The key becomes the final segment of the
# broker key the row is projected under, so it is held to the character set the
# broker accepts for a key segment ('A'-'Z', 'a'-'z', '0'-'9', '-', '_', '/',
# '='). A dot, whitespace or a subject wildcard ('*', '>') would make the broker
# reject the key and silently drop the projection, so such a key is rejected here
# at write time instead. ``fullmatch`` is used so a trailing newline cannot slip
# through.
PARAMS_KEY_PATTERN = re.compile(r"[A-Za-z0-9_/=-]+")


def _validate_params_key(params_key: str) -> None:
    """Rejects a params_key the downstream broker could not represent.

    A key outside ``PARAMS_KEY_PATTERN`` (for example one carrying a dot,
    whitespace or a wildcard) would be dropped by the broker projection without
    error, so it is rejected here with a message naming the offending key.
    """
    if not isinstance(params_key, str) or not PARAMS_KEY_PATTERN.fullmatch(params_key):
        raise ValueError(
            f"params_key '{params_key}' must be a non-empty string containing "
            "only the characters [A-Za-z0-9_/=-]."
        )


def _wire_key(params_kind: str) -> Optional[str]:
    """Returns the top-level key a kind nests under in the wire shape.

    Flat kinds contribute their fields at the top level and have no wrapping
    key, so they return ``None``. Nested kinds return the dedicated key their
    values sit under. The mapping is taken from ``NESTED_GROUPS`` so the wire
    shape stays defined in a single place.
    """
    return NESTED_GROUPS.get(params_kind)


def to_wire_shape(params_kind: str, values: dict) -> dict:
    """Shapes a group's values into the fragment downstream services read.

    Flat kinds keep their fields at the top level; nested kinds are wrapped
    under their dedicated key. The result is the exact fragment a consumer
    merges into the parameter set, so a per-key value can be stored and served
    without the consumer knowing whether a kind is flat or nested.
    """
    out_key = _wire_key(params_kind)
    if out_key is None:
        return values
    return {out_key: values}


def from_wire_shape(params_kind: str, stored: dict) -> dict:
    """Recovers a group's bare values from its wire-shaped fragment.

    The inverse of ``to_wire_shape``. A nested kind's values are taken from
    under its dedicated key; a fragment that still carries the bare values
    (for example a row written before values were shaped on write) is returned
    unchanged, so an older row is read without a migration.
    """
    out_key = _wire_key(params_kind)
    if out_key is None:
        return stored
    if isinstance(stored, dict) and out_key in stored:
        return stored[out_key]
    return stored


def params_kind_catalog() -> dict:
    """Returns the catalog of parameter kinds accepted on the write path.

    This is the single source the write-path validation uses. A consumer that
    needs to validate a kind (for example the admission webhook) can read it
    here instead of keeping its own copy.
    """
    return {"kinds": sorted(VALID_GROUPS)}


def _deep_merge(base: dict, patch: dict) -> dict:
    """Return a new dict with ``patch`` overlaid on ``base`` field by field.

    Nested dictionaries are merged recursively so that a partial change never
    resets sibling fields. The inputs are not mutated (pure transform).
    """
    merged = dict(base)
    for key, value in patch.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class EragSystemFingerprintController:
    """Stores and retrieves pipeline parameter groups in Postgres.

    The store is keyed by the composite ``(pipeline, tenant, params_key)``.
    Each row holds one parameter group (llm, retriever, a guardrail set, ...)
    as a JSONB ``values`` payload.
    """

    def __init__(self, host, port, db_name, user=None, password=None,
                 pipeline: str = "default", tenant: str = "_global",
                 template_language: str = "en"):
        self.host = host
        self.port = int(port)
        self.db_name = db_name
        self.user = user
        self.password = password
        self.pipeline = pipeline
        self.tenant = tenant
        self.pool: Optional[asyncpg.Pool] = None

        template_language = (template_language or "en").lower()
        if template_language not in ["en", "pl"]:
            raise ValueError("Unsupported template language. Only 'en' and 'pl' are supported.")
        self.template_language = template_language

    def _resolve_scope(self, pipeline: Optional[str],
                       tenant: Optional[str]) -> Tuple[str, str]:
        """Resolves the (pipeline, tenant) a call targets.

        A value left as ``None`` falls back to the controller's own
        configuration; an explicit value overrides it. An explicit value that
        is empty or not a string is rejected rather than silently ignored, so a
        caller never gets false confidence that a blank scope hit its default.
        Both dimensions become part of the key a downstream broker projects the
        row under, so the effective value (whether from an explicit override or
        from the configured default) must match ``SCOPE_PATTERN``.  This catches
        env-derived defaults that contain KV-illegal characters before they can
        produce a key the broker cannot represent.
        """
        if pipeline is not None:
            if not isinstance(pipeline, str) or not pipeline:
                raise ValueError("pipeline must be a non-empty string when provided.")
        if tenant is not None:
            if not isinstance(tenant, str) or not tenant:
                raise ValueError("tenant must be a non-empty string when provided.")
        effective_pipeline = pipeline if pipeline is not None else self.pipeline
        effective_tenant = tenant if tenant is not None else self.tenant
        if not isinstance(effective_pipeline, str) or not SCOPE_PATTERN.fullmatch(effective_pipeline):
            raise ValueError(
                "pipeline must be a non-empty string matching [A-Za-z0-9_-]; "
                "check the SYSTEM_FINGERPRINT_PIPELINE configuration."
            )
        if not isinstance(effective_tenant, str) or not SCOPE_PATTERN.fullmatch(effective_tenant):
            raise ValueError(
                "tenant must be a non-empty string matching [A-Za-z0-9_-]; "
                "check the SYSTEM_FINGERPRINT_TENANT configuration."
            )
        return effective_pipeline, effective_tenant

    def _prompt_template_model(self) -> Type[BaseModel]:
        return PromptTemplatePlParams if self.template_language == "pl" else PromptTemplateEnParams

    def _model_for(self, params_key: str) -> Type[BaseModel]:
        if params_key == "prompt_template":
            return self._prompt_template_model()
        return GROUP_MODELS[params_key]

    async def _connect_with_retry(self) -> asyncpg.Pool:
        """Opens the connection pool, retrying while the database is unready.

        A database that is still starting up raises on connect; that is treated
        as transient and retried a bounded number of times so the microservice
        waits for the database instead of crash looping. Errors that will not
        resolve by waiting (bad credentials, missing database or role) are
        re-raised immediately so a misconfiguration fails fast instead of being
        buried under minutes of retries. The last transient error is re-raised
        once the retries are exhausted.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, CONNECT_RETRIES + 1):
            try:
                return await asyncpg.create_pool(
                    host=self.host,
                    port=self.port,
                    database=self.db_name,
                    user=self.user,
                    password=self.password,
                    min_size=1,
                    max_size=8,
                    command_timeout=STATEMENT_TIMEOUT_SECONDS,
                )
            except (asyncpg.InvalidAuthorizationSpecificationError,
                    asyncpg.InvalidPasswordError,
                    asyncpg.InvalidCatalogNameError):
                # Credentials, database name or role are wrong; waiting will
                # not fix it, so surface the configuration error right away.
                logger.exception("Database configuration is invalid")
                raise
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Database not ready (attempt {attempt}/{CONNECT_RETRIES}): {e}. "
                    f"Retrying in {CONNECT_RETRY_DELAY_SECONDS}s.")
                if attempt < CONNECT_RETRIES:
                    await asyncio.sleep(CONNECT_RETRY_DELAY_SECONDS)
        raise Exception(
            f"Database not reachable after {CONNECT_RETRIES} attempts: {last_error}") from last_error

    async def init_async(self) -> None:
        """Connects to Postgres, ensures the schema, and seeds defaults."""
        try:
            self.pool = await self._connect_with_retry()
            await self._setup_schema()
            await self._check_and_ingest_defaults()
        except Exception as e:
            err_msg = "Failed to initialize Postgres"
            logger.exception(err_msg)
            # Avoid leaking the pool if setup fails after it was created
            # (e.g. a schema error during a crash-looping startup).
            await self.close()
            raise Exception(f"{err_msg}: {e}") from e

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            logger.info("Connection to database cluster closed.")

    async def _validate(self) -> None:
        """Confirms the database is reachable with a cheap query.

        Runs ``SELECT 1`` over the pool and raises when the pool has not been
        opened yet or the query fails. Registered as the microservice's health
        validate method, so ``/v1/health_check`` reports the database backend
        instead of process liveness alone. The query is bounded by a short
        timeout so a stalled connection fails fast rather than blocking the
        health handler.
        """
        if self.pool is None:
            raise Exception("Connection pool is not initialized.")

        async def _run() -> None:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

        try:
            await asyncio.wait_for(_run(), timeout=VALIDATE_TIMEOUT_SECONDS)
            logger.debug("Connected to database cluster.")
        except Exception as e:
            logger.exception("Problem connecting to database cluster.")
            raise Exception("Problem connecting to database cluster.") from e

    async def _setup_schema(self) -> None:
        """Creates the ``fingerprint_config`` table and its NOTIFY trigger.

        The trigger emits a payload of (pipeline, tenant, params_key) on every
        INSERT/UPDATE for consumers listening on the NOTIFY channel.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(SCHEMA_DDL)
        except Exception as e:
            err_msg = "Failed to set up database schema"
            logger.exception(err_msg)
            raise Exception(f"{err_msg}: {e}")

    async def _check_and_ingest_defaults(self) -> None:
        """Seeds a default row for every group that is not yet present.

        The full group set is seeded under the controller's own scope. Every
        entry in ``EXTRA_SCOPED_SEEDS`` is additionally seeded under its own
        scope so a consumer reading a non-default (pipeline, tenant) finds its
        row present on first read instead of a 404.
        """
        try:
            defaults = self._default_groups()
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Seed missing rows at the current next version (under the
                    # advisory lock) so a group introduced after users have
                    # already bumped versions never gets a lower version than
                    # its siblings, preserving the monotonic invariant.
                    seed_version = await self._next_version(conn)
                    for params_key, values in defaults.items():
                        await self._seed_default_row(
                            conn, self.pipeline, self.tenant,
                            params_key, params_key, values, seed_version)
                    # Group the extra seeds by scope so every key in one scope
                    # shares a single next version, matching how the default
                    # scope seeds all its groups at one version.
                    extra_scopes: Dict[Tuple[str, str], List[str]] = {}
                    for pipeline, tenant, params_key in EXTRA_SCOPED_SEEDS:
                        extra_scopes.setdefault((pipeline, tenant), []).append(params_key)
                    for (pipeline, tenant), params_keys in extra_scopes.items():
                        # Version is per (pipeline, tenant), so each extra scope
                        # gets its own next version under its own advisory lock.
                        extra_version = await self._next_version(conn, pipeline, tenant)
                        for params_key in params_keys:
                            await self._seed_default_row(
                                conn, pipeline, tenant, params_key, params_key,
                                self._default_values_for(params_key), extra_version)
        except Exception as e:
            err_msg = "Failed to check and ingest defaults"
            logger.exception(err_msg)
            raise Exception(f"{err_msg}: {e}")

    async def _seed_default_row(self, conn, pipeline: str, tenant: str,
                                params_key: str, params_kind: str,
                                values: dict, version: int) -> None:
        """Inserts one default row, leaving an existing row untouched.

        The value is stored in wire shape so a nested kind is wrapped under its
        dedicated key. ``ON CONFLICT DO NOTHING`` keeps the call idempotent, so
        a restart never overwrites a row an admin has since edited.
        """
        await conn.execute(
            """
            INSERT INTO fingerprint_config
                (pipeline, tenant, params_key, params_kind,
                 values, schema_version, version, updated_at)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
            ON CONFLICT (pipeline, tenant, params_key)
            DO NOTHING
            """,
            pipeline,
            tenant,
            params_key,
            params_kind,
            json.dumps(to_wire_shape(params_kind, values)),
            SCHEMA_VERSION,
            version,
            datetime.now(timezone.utc),
        )

    def _default_values_for(self, params_kind: str) -> dict:
        """Builds the default value payload for a single parameter kind.

        The guardrail kinds are assembled from their per-scanner models so that
        each scanner starts disabled with its own defaults. prompt_template is
        resolved through the language-dependent model. An unknown kind raises,
        since only the known groups have a defined default shape.
        """
        if params_kind in _SIMPLE_DEFAULT_MODELS:
            return _SIMPLE_DEFAULT_MODELS[params_kind]().model_dump()
        if params_kind == "prompt_template":
            return self._prompt_template_model()().model_dump()
        if params_kind == "input_guard":
            return LLMGuardInputGuardrailParams(
                anonymize=AnonymizeModel(),
                ban_substrings=BanSubstringsModel(),
                ban_topics=BanTopicsModel(),
                code=CodeModel(),
                invisible_text=InvisibleText(),
                prompt_injection=PromptInjectionModel(),
                regex=RegexModel(),
                secrets=SecretsModel(),
                sentiment=SentimentModel(),
                token_limit=TokenLimitModel(),
                toxicity=ToxicityModel(),
            ).model_dump()
        if params_kind == "output_guard":
            return LLMGuardOutputGuardrailParams(
                ban_substrings=BanSubstringsModel(),
                ban_topics=BanTopicsModel(),
                bias=BiasModel(),
                code=CodeModel(),
                deanonymize=DeanonymizeModel(),
                json_scanner=JSONModel(),
                malicious_urls=MaliciousURLsModel(),
                no_refusal=NoRefusalModel(),
                no_refusal_light=NoRefusalLightModel(),
                reading_time=ReadingTimeModel(),
                factual_consistency=FactualConsistencyModel(),
                regex=RegexModel(),
                relevance=RelevanceModel(),
                sensitive=SensitiveModel(),
                sentiment=SentimentModel(),
                toxicity=ToxicityModel(),
                url_reachability=URLReachabilityModel(),
            ).model_dump()
        if params_kind == "dataprep_guard":
            return LLMGuardDataprepGuardrailParams(
                ban_substrings=BanSubstringsModel(),
                ban_topics=BanTopicsModel(),
                code=CodeModel(),
                invisible_text=InvisibleText(),
                prompt_injection=PromptInjectionModel(),
                regex=RegexModel(),
                secrets=SecretsModel(),
                sentiment=SentimentModel(),
                token_limit=TokenLimitModel(),
                toxicity=ToxicityModel(),
            ).model_dump()
        raise ValueError(f"Unknown params_kind: {params_kind}")

    def _default_groups(self) -> Dict[str, dict]:
        """Builds the default value payload for each parameter group."""
        return {params_key: self._default_values_for(params_key) for params_key in VALID_GROUPS}

    async def ensure_keys(self, keys: List[dict], pipeline: Optional[str] = None,
                          tenant: Optional[str] = None) -> None:
        """Seeds a default row for each requested key that is not yet present.

        ``keys`` is a list of ``{params_key, params_kind}`` items. Each key is
        inserted with the default payload for its kind; rows that already exist
        are left untouched, so the call is idempotent and safe to repeat. A
        pipeline and tenant may be supplied to target a store other than the
        controller's own; both default to the controller's configuration. An
        unknown or missing ``params_kind`` raises before any write.
        """
        target_pipeline, target_tenant = self._resolve_scope(pipeline, tenant)

        if not isinstance(keys, list):
            raise ValueError("keys must be a list of {params_key, params_kind} items.")

        prepared = []
        for item in keys:
            if not isinstance(item, dict):
                raise ValueError("Each key must be a {params_key, params_kind} object.")
            params_key = item.get("params_key")
            params_kind = item.get("params_kind")
            if not isinstance(params_key, str) or not isinstance(params_kind, str) \
                    or not params_key or not params_kind:
                raise ValueError("Each key requires a non-empty string params_key and params_kind.")
            _validate_params_key(params_key)
            if params_kind not in VALID_GROUPS:
                raise ValueError(f"Unknown params_kind: {params_kind}")
            prepared.append((params_key, params_kind, self._default_values_for(params_kind)))

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Seed at the current next version (under the advisory lock)
                    # so a key added after users have bumped versions never gets
                    # a lower version than its siblings.
                    seed_version = await self._next_version(conn, target_pipeline, target_tenant)
                    now = datetime.now(timezone.utc)
                    rows = [
                        (target_pipeline, target_tenant, params_key, params_kind,
                         json.dumps(to_wire_shape(params_kind, values)),
                         SCHEMA_VERSION, seed_version, now)
                        for params_key, params_kind, values in prepared
                    ]
                    # One batched round-trip for the whole set of keys.
                    await conn.executemany(
                        """
                        INSERT INTO fingerprint_config
                            (pipeline, tenant, params_key, params_kind,
                             values, schema_version, version, updated_at)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
                        ON CONFLICT (pipeline, tenant, params_key)
                        DO NOTHING
                        """,
                        rows,
                    )
        except Exception as e:
            err_msg = "Failed to ensure keys"
            logger.exception(err_msg)
            raise Exception(f"{err_msg}: {e}") from e

    async def _read_group(self, conn, params_key: str, pipeline: Optional[str] = None,
                          tenant: Optional[str] = None) -> Optional[dict]:
        """Returns the stored bare ``values`` and ``params_kind`` for one group.

        Returns ``None`` when no row exists for the key. The kind is carried
        alongside the values so a write can reuse the kind a key was seeded
        with instead of assuming the key names its own kind. The stored value
        is unwrapped back to its bare form so the merge and validation on the
        write path operate on the plain group fields. Pipeline and tenant
        default to the controller's own configuration.
        """
        row = await conn.fetchrow(
            """
            SELECT values, params_kind
            FROM fingerprint_config
            WHERE pipeline = $1 AND tenant = $2 AND params_key = $3
            """,
            pipeline or self.pipeline,
            tenant or self.tenant,
            params_key,
        )
        if row is None:
            return None
        stored = row["values"]
        values = json.loads(stored) if isinstance(stored, str) else dict(stored)
        return {
            "values": from_wire_shape(row["params_kind"], values),
            "params_kind": row["params_kind"],
        }

    def _resolve_kind(self, params_key: str, requested_kind: Optional[str],
                      existing_kind: Optional[str]) -> Optional[str]:
        """Determines which parameter kind a write should be validated against.

        A key is free-form (for example ``llm_primary``), so its kind is not
        always its name. The kind is taken, in order, from the kind supplied on
        the item, then the kind the key was already stored with, then the key
        itself when it happens to be a canonical group name. A key with no
        resolvable kind is unknown and returns ``None`` so the caller skips it.
        An explicitly supplied kind outside the catalog raises, as does a kind
        that contradicts a canonical key (a canonical key names its own kind, so
        storing it under a different kind would produce an inconsistent row) or
        one that contradicts the kind the key was already stored with (changing
        a key's kind would repurpose the row and drop its fields).
        """
        if requested_kind is not None:
            if requested_kind not in VALID_GROUPS:
                raise ValueError(f"Unknown params_kind: {requested_kind}")
            if params_key in VALID_GROUPS and requested_kind != params_key:
                raise ValueError(
                    f"params_kind '{requested_kind}' does not match canonical "
                    f"params_key '{params_key}'.")
            if existing_kind is not None and requested_kind != existing_kind:
                raise ValueError(
                    f"params_kind '{requested_kind}' does not match the stored "
                    f"kind '{existing_kind}' for params_key '{params_key}'.")
            return requested_kind
        if existing_kind is not None:
            return existing_kind
        if params_key in VALID_GROUPS:
            return params_key
        return None

    async def store_arguments(self, inputs: List, pipeline: Optional[str] = None,
                              tenant: Optional[str] = None) -> None:
        """Applies a field-level merge for each provided parameter group.

        ``inputs`` is a list of ``{name, data}`` items, where ``name`` is the
        target ``params_key`` and an optional ``params_kind`` selects the value
        model for a free-form key. Keys with no resolvable kind and null data
        are silently ignored. Each recognised group is merged into the stored
        values (siblings preserved), validated through its kind's value-object
        model, and written with a monotonically increasing version. A group
        whose merged value is unchanged is skipped without a version bump. A
        pipeline and tenant may be supplied to target a store other than the
        controller's own; both default to the controller's configuration.
        """
        target_pipeline, target_tenant = self._resolve_scope(pipeline, tenant)
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    next_version = await self._next_version(
                        conn, target_pipeline, target_tenant)
                    wrote_any = False
                    for item in inputs:
                        params_key = item.name
                        data = item.data
                        if data is None:
                            continue

                        row = await self._read_group(
                            conn, params_key, target_pipeline, target_tenant)
                        existing = row["values"] if row else {}
                        existing_kind = row["params_kind"] if row else None
                        params_kind = self._resolve_kind(
                            params_key, getattr(item, "params_kind", None), existing_kind)
                        if params_kind is None:
                            continue
                        _validate_params_key(params_key)

                        merged = _deep_merge(existing, data)
                        model = self._model_for(params_kind)
                        canonical = model(**merged).model_dump()

                        if canonical == existing:
                            logger.warning(
                                f"Provided duplicate parameters. Skipping storage for {params_key}")
                            continue

                        await conn.execute(
                            """
                            INSERT INTO fingerprint_config
                                (pipeline, tenant, params_key, params_kind,
                                 values, schema_version, version, updated_at)
                            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
                            ON CONFLICT (pipeline, tenant, params_key)
                            DO UPDATE SET
                                params_kind = EXCLUDED.params_kind,
                                values = EXCLUDED.values,
                                schema_version = EXCLUDED.schema_version,
                                version = EXCLUDED.version,
                                updated_at = EXCLUDED.updated_at
                            """,
                            target_pipeline,
                            target_tenant,
                            params_key,
                            params_kind,
                            json.dumps(to_wire_shape(params_kind, canonical)),
                            SCHEMA_VERSION,
                            next_version,
                            datetime.now(timezone.utc),
                        )
                        wrote_any = True

                    if wrote_any:
                        logger.info(f"Input {inputs} stored successfully.")
        except ValueError:
            raise
        except Exception as e:
            err_msg = "Failed to store document"
            logger.exception(err_msg)
            raise Exception(f"{err_msg}: {e}")

    async def read_group(self, params_key: str, pipeline: Optional[str] = None,
                         tenant: Optional[str] = None) -> Optional[dict]:
        """Returns one stored group for a ``(pipeline, tenant, params_key)``.

        The response carries the stored ``values`` verbatim (the same payload
        the change-notification consumers read per key) together with the
        group's ``params_kind`` and ``version``. The stored value is already in
        wire shape: a flat kind carries its bare fields, a nested kind carries
        its values under its dedicated key, so a consumer can merge it into the
        parameter set without knowing the kind's layout. Pipeline and tenant
        default to the controller's own configuration; an explicit empty or
        malformed value is rejected rather than falling back to the default.
        Returns ``None`` when the key has no row, which the handler turns into a
        404.
        """
        target_pipeline, target_tenant = self._resolve_scope(pipeline, tenant)
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT params_key, params_kind, values, version
                    FROM fingerprint_config
                    WHERE pipeline = $1 AND tenant = $2 AND params_key = $3
                    """,
                    target_pipeline,
                    target_tenant,
                    params_key,
                )
        except Exception as e:
            err_msg = "Failed to read group"
            logger.exception(err_msg)
            raise Exception(f"{err_msg}: {e}")

        if row is None:
            return None
        stored = row["values"]
        values = json.loads(stored) if isinstance(stored, str) else dict(stored)
        return {
            "params_key": row["params_key"],
            "params_kind": row["params_kind"],
            "version": row["version"],
            "values": values,
        }

    async def _next_version(self, conn, pipeline: Optional[str] = None,
                            tenant: Optional[str] = None) -> int:
        """Computes the next monotonic version for the (pipeline, tenant).

        A transaction-scoped advisory lock keyed on the (pipeline, tenant)
        serializes concurrent writers so two transactions cannot read the same
        MAX and write the same version. The lock is released automatically when
        the surrounding transaction commits or rolls back. The two-key int4
        form hashes each dimension separately, avoiding a text separator (a
        Postgres ``text`` value may not contain a NUL byte). Both keys default
        to the controller's own configuration.
        """
        pipeline = pipeline or self.pipeline
        tenant = tenant or self.tenant
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1), hashtext($2))",
            pipeline,
            tenant,
        )
        current = await conn.fetchval(
            """
            SELECT COALESCE(MAX(version), 0)
            FROM fingerprint_config
            WHERE pipeline = $1 AND tenant = $2
            """,
            pipeline,
            tenant,
        )
        return int(current) + 1


SCHEMA_DDL = f"""
CREATE TABLE IF NOT EXISTS fingerprint_config (
    pipeline       text   NOT NULL,
    tenant         text   NOT NULL DEFAULT '_global',
    params_key     text   NOT NULL,
    params_kind    text   NOT NULL,
    values         jsonb  NOT NULL DEFAULT '{{}}'::jsonb,
    schema_version int    NOT NULL DEFAULT 1,
    version        bigint NOT NULL DEFAULT 1,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (pipeline, tenant, params_key)
);

CREATE OR REPLACE FUNCTION notify_fingerprint_config_changed()
RETURNS trigger AS $$
DECLARE
    payload json;
BEGIN
    payload := json_build_object(
        'pipeline', NEW.pipeline,
        'tenant', NEW.tenant,
        'params_key', NEW.params_key
    );
    PERFORM pg_notify('{NOTIFY_CHANNEL}', payload::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS fingerprint_config_notify ON fingerprint_config;
CREATE TRIGGER fingerprint_config_notify
AFTER INSERT OR UPDATE ON fingerprint_config
FOR EACH ROW EXECUTE FUNCTION notify_fingerprint_config_changed();
"""
