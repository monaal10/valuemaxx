"""OUT-C: install_run_id_injection — copy-on-write merge of run_id into outbound kwargs."""

from __future__ import annotations

import sys
import types

import pytest
from valuemaxx.core import RunId, active_run_id
from valuemaxx.outcomes.instrument.injection import install_run_id_injection
from valuemaxx.outcomes.schema import RunIdInjectionSpec


@pytest.fixture
def stripe_like() -> types.ModuleType:
    """A throwaway 'stripe' module with a PaymentIntent.create that echoes its kwargs."""
    mod = types.ModuleType("stripe_like")

    class PaymentIntent:
        @staticmethod
        def create(**kwargs: object) -> dict[str, object]:
            return {"received_kwargs": kwargs}

    mod.PaymentIntent = PaymentIntent  # type: ignore[attr-defined]
    sys.modules["stripe_like"] = mod
    yield mod
    sys.modules.pop("stripe_like", None)


def _spec(sdk_call: str = "stripe_like.PaymentIntent.create") -> RunIdInjectionSpec:
    return RunIdInjectionSpec(
        sdk_call=sdk_call,
        inject_into="metadata.run_id",
        webhook_event="payment_intent.succeeded",
        extract_from="data.object.metadata.run_id",
    )


def test_run_id_merged_into_outbound_kwargs(stripe_like: types.ModuleType) -> None:
    """With an active run, run_id is merged into the inject_into path of the call kwargs."""
    install_run_id_injection([_spec()])
    token = active_run_id.set(RunId("run-7"))
    try:
        result = stripe_like.PaymentIntent.create(amount=1000, metadata={"customer": "c1"})
    finally:
        active_run_id.reset(token)
    received = result["received_kwargs"]
    assert received["metadata"]["run_id"] == "run-7"
    # the pre-existing metadata key is preserved (deep merge, not replace)
    assert received["metadata"]["customer"] == "c1"


def test_injection_is_copy_on_write(stripe_like: types.ModuleType) -> None:
    """The caller's own metadata dict is never mutated (copy-on-write)."""
    install_run_id_injection([_spec()])
    callers_metadata: dict[str, object] = {"customer": "c1"}
    token = active_run_id.set(RunId("run-7"))
    try:
        stripe_like.PaymentIntent.create(amount=1000, metadata=callers_metadata)
    finally:
        active_run_id.reset(token)
    # the caller's dict must be untouched — no run_id leaked into it
    assert callers_metadata == {"customer": "c1"}


def test_no_active_run_means_no_injection(stripe_like: types.ModuleType) -> None:
    """With no active run, the call passes through unchanged (no run_id added)."""
    install_run_id_injection([_spec()])
    result = stripe_like.PaymentIntent.create(amount=1000, metadata={"customer": "c1"})
    received = result["received_kwargs"]
    assert "run_id" not in received["metadata"]


def test_injection_creates_missing_parent_path(stripe_like: types.ModuleType) -> None:
    """When inject_into's parent path is absent, it is created without touching siblings."""
    install_run_id_injection([_spec()])
    token = active_run_id.set(RunId("run-9"))
    try:
        result = stripe_like.PaymentIntent.create(amount=1000)  # no metadata kwarg at all
    finally:
        active_run_id.reset(token)
    received = result["received_kwargs"]
    assert received["metadata"]["run_id"] == "run-9"


def test_unresolved_sdk_call_warns_not_silent() -> None:
    """A non-importable sdk_call is reported as unresolved (named), never a silent no-op."""
    report = install_run_id_injection([_spec(sdk_call="nope.NotReal.create")])
    assert "nope.NotReal.create" in report.unresolved
    assert report.installed == ()


def test_host_error_is_not_swallowed(stripe_like: types.ModuleType) -> None:
    """If the wrapped sdk_call raises, the error propagates (injection never hides it)."""

    def boom(**_kwargs: object) -> None:
        raise RuntimeError("stripe down")

    stripe_like.PaymentIntent.boom = staticmethod(boom)  # type: ignore[attr-defined]
    install_run_id_injection([_spec(sdk_call="stripe_like.PaymentIntent.boom")])
    token = active_run_id.set(RunId("run-7"))
    try:
        with pytest.raises(RuntimeError, match="stripe down"):
            stripe_like.PaymentIntent.boom(amount=1)
    finally:
        active_run_id.reset(token)


def test_installed_targets_reported(stripe_like: types.ModuleType) -> None:
    """A resolved sdk_call is reported as installed."""
    report = install_run_id_injection([_spec()])
    assert "stripe_like.PaymentIntent.create" in report.installed
