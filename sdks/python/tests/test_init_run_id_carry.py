"""SDK — init() wires the T2 baggage producer + T3 run_id injection (deterministic carry).

``init()`` already establishes the ambient run id (T1) via ``track.run``. These tests pin
the two carry channels it must ALSO install so deterministic binding is automatic:

* **T3** — ``run_id_injection`` specs (from the onboarded outcomes.yaml) auto-wrap the
  declared echoing SDK calls so the run_id round-trips through the external object.
* **T2** — ``baggage_targets`` auto-wrap outbound HTTP so the run_id rides W3C baggage
  across a live service hop.

Both are fail-open (an install error is a warning, never raised) and both surface an
unresolved target as a named warning — never a silent no-op (H10).
"""

from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from valuemaxx.core import RunId, active_run_id
from valuemaxx.core.ids import TenantId
from valuemaxx.core.wire import BAGGAGE_RUN_ID_KEY
from valuemaxx.outcomes.schema import RunIdInjectionSpec
from valuemaxx.sdk import InitResult, init

if TYPE_CHECKING:
    from collections.abc import Iterator


def _tenant() -> TenantId:
    return TenantId(uuid4())


@pytest.fixture
def echoing_module() -> Iterator[types.ModuleType]:
    """A throwaway module with a stripe-like create + an http-like request that echo kwargs."""
    mod = types.ModuleType("carry_mod")

    class PaymentIntent:
        @staticmethod
        def create(**kwargs: object) -> dict[str, object]:
            return {"received_kwargs": kwargs}

    class HttpClient:
        @staticmethod
        def request(**kwargs: object) -> dict[str, object]:
            return {"received_kwargs": kwargs}

    mod.PaymentIntent = PaymentIntent  # type: ignore[attr-defined]
    mod.HttpClient = HttpClient  # type: ignore[attr-defined]
    sys.modules["carry_mod"] = mod
    yield mod
    sys.modules.pop("carry_mod", None)


def test_t3_injection_specs_are_installed(echoing_module: types.ModuleType) -> None:
    """test_t3_injection_specs_are_installed: a declared sdk_call gets run_id merged in."""
    spec = RunIdInjectionSpec(
        sdk_call="carry_mod.PaymentIntent.create",
        inject_into="metadata.atm_run_id",
        webhook_event="payment_intent.succeeded",
        extract_from="data.object.metadata.atm_run_id",
    )
    init(
        tenant_id=_tenant(),
        ingest_key="k",
        endpoint="https://x.example",
        run_id_injection_specs=[spec],
    )
    token = active_run_id.set(RunId("run-3"))
    try:
        result = echoing_module.PaymentIntent.create(amount=1, metadata={"c": "1"})
    finally:
        active_run_id.reset(token)
    assert result["received_kwargs"]["metadata"]["atm_run_id"] == "run-3"


def test_t2_baggage_targets_are_installed(echoing_module: types.ModuleType) -> None:
    """test_t2_baggage_targets_are_installed: a declared HTTP target rides run_id on baggage."""
    init(
        tenant_id=_tenant(),
        ingest_key="k",
        endpoint="https://x.example",
        baggage_targets=["carry_mod.HttpClient.request"],
    )
    token = active_run_id.set(RunId("run-5"))
    try:
        result = echoing_module.HttpClient.request(url="u")
    finally:
        active_run_id.reset(token)
    assert result["received_kwargs"]["headers"]["baggage"] == f"{BAGGAGE_RUN_ID_KEY}=run-5"


def test_unresolved_injection_target_warns() -> None:
    """test_unresolved_injection_target_warns: a bad sdk_call is a named warning, not silent."""
    spec = RunIdInjectionSpec(
        sdk_call="nope.NotReal.create",
        inject_into="metadata.atm_run_id",
        webhook_event="e",
        extract_from="data.x",
    )
    result = init(
        tenant_id=_tenant(),
        ingest_key="k",
        endpoint="https://x.example",
        run_id_injection_specs=[spec],
    )
    assert any("nope.NotReal.create" in w for w in result.warnings)


def test_unresolved_baggage_target_warns() -> None:
    """test_unresolved_baggage_target_warns: a bad baggage target is a named warning."""
    result = init(
        tenant_id=_tenant(),
        ingest_key="k",
        endpoint="https://x.example",
        baggage_targets=["nope.NotReal.request"],
    )
    assert any("nope.NotReal.request" in w for w in result.warnings)


def test_no_carry_args_is_a_normal_init() -> None:
    """test_no_carry_args_is_a_normal_init: omitting both leaves init() behaviour unchanged."""
    result = init(tenant_id=_tenant(), ingest_key="k", endpoint="https://x.example")
    assert isinstance(result, InitResult)


def test_carry_install_is_fail_open(
    echoing_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test_carry_install_is_fail_open: an installer that raises is swallowed as a warning."""

    def _boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("install blew up")

    monkeypatch.setattr("valuemaxx.sdk._bootstrap.install_run_id_baggage", _boom)
    result = init(
        tenant_id=_tenant(),
        ingest_key="k",
        endpoint="https://x.example",
        baggage_targets=["carry_mod.HttpClient.request"],
    )
    assert isinstance(result, InitResult)
    assert any("internal" in w.lower() or "blew up" in w for w in result.warnings)
