# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import importlib


def test_health_validate_is_registered_on_every_endpoint():
    """Every registration wires the DB-backed validate method.

    The framework runs ``validate_methods`` from ``/v1/health_check``, so the
    controller's ``_validate`` must be passed to ``register_microservice`` for
    the health check to report Postgres reachability. The register mock records
    the kwargs each registration was called with.
    """
    from comps.cores.mega import micro_service

    calls = []
    original = micro_service.register_microservice

    def recording_register(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    from comps.system_fingerprint.utils.erag_system_fingerprint import (
        EragSystemFingerprintController,
    )

    micro_service.register_microservice = recording_register
    try:
        import comps.system_fingerprint.erag_system_fingerprint_microservice as module
        importlib.reload(module)
    finally:
        micro_service.register_microservice = original

    assert calls, "The microservice must register at least one endpoint."
    for kwargs in calls:
        methods = kwargs.get("validate_methods") or []
        funcs = [getattr(m, "__func__", m) for m in methods]
        assert EragSystemFingerprintController._validate in funcs, \
            "Every endpoint must wire the controller's _validate, so " \
            "/v1/health_check reports Postgres reachability."
