"""OUT-C/T2: install_run_id_baggage — stamp the active run_id onto the W3C baggage header.

The T2 producer wraps an outbound HTTP client call so a live service→service request
carries the active run_id on the W3C ``baggage`` header (``valuemaxx.run_id=<id>``). The
receiving service's ingress parses it back into the cascade's baggage map, where the T2
resolver binds it ``exact``. Mirrors the T3 injector's invariants exactly: copy-on-write
on the caller's headers, pass-through with no active run, unresolved target warns (never a
silent no-op), and a host error is never swallowed.
"""

from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING, cast

import pytest
from valuemaxx.core import RunId, active_run_id
from valuemaxx.core.wire import BAGGAGE_RUN_ID_KEY
from valuemaxx.outcomes.instrument.baggage import install_run_id_baggage

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def http_like() -> Iterator[types.ModuleType]:
    """A throwaway http client whose ``request`` echoes its kwargs (incl. headers)."""
    mod = types.ModuleType("http_like")

    class Client:
        @staticmethod
        def request(**kwargs: object) -> dict[str, object]:
            return {"received_kwargs": kwargs}

    mod.Client = Client  # type: ignore[attr-defined]
    sys.modules["http_like"] = mod
    yield mod
    sys.modules.pop("http_like", None)


def _headers(result: dict[str, object]) -> dict[str, str]:
    kwargs = result["received_kwargs"]
    assert isinstance(kwargs, dict)
    headers: object = cast("dict[str, object]", kwargs).get("headers", {})
    assert isinstance(headers, dict)
    return cast("dict[str, str]", headers)


def test_run_id_stamped_onto_baggage_header(http_like: types.ModuleType) -> None:
    """With an active run, the baggage header carries valuemaxx.run_id=<id>."""
    install_run_id_baggage(["http_like.Client.request"])
    token = active_run_id.set(RunId("run-7"))
    try:
        result = http_like.Client.request(url="https://svc/b")
    finally:
        active_run_id.reset(token)
    assert _headers(result)["baggage"] == f"{BAGGAGE_RUN_ID_KEY}=run-7"


def test_existing_baggage_members_preserved(http_like: types.ModuleType) -> None:
    """An existing baggage header keeps its members; our key is appended (W3C list)."""
    install_run_id_baggage(["http_like.Client.request"])
    token = active_run_id.set(RunId("run-7"))
    try:
        result = http_like.Client.request(url="u", headers={"baggage": "team=payments"})
    finally:
        active_run_id.reset(token)
    members = set(_headers(result)["baggage"].split(","))
    assert members == {"team=payments", f"{BAGGAGE_RUN_ID_KEY}=run-7"}


def test_run_id_already_present_is_not_duplicated(http_like: types.ModuleType) -> None:
    """If the baggage already carries our key, it is replaced, not duplicated."""
    install_run_id_baggage(["http_like.Client.request"])
    token = active_run_id.set(RunId("run-9"))
    try:
        result = http_like.Client.request(
            url="u", headers={"baggage": f"{BAGGAGE_RUN_ID_KEY}=stale,team=x"}
        )
    finally:
        active_run_id.reset(token)
    members = _headers(result)["baggage"].split(",")
    run_id_members = [m for m in members if m.startswith(f"{BAGGAGE_RUN_ID_KEY}=")]
    assert run_id_members == [f"{BAGGAGE_RUN_ID_KEY}=run-9"]
    assert "team=x" in members


def test_baggage_is_copy_on_write(http_like: types.ModuleType) -> None:
    """The caller's own headers dict is never mutated (copy-on-write)."""
    install_run_id_baggage(["http_like.Client.request"])
    callers_headers: dict[str, str] = {"authorization": "Bearer x"}
    token = active_run_id.set(RunId("run-7"))
    try:
        http_like.Client.request(url="u", headers=callers_headers)
    finally:
        active_run_id.reset(token)
    assert callers_headers == {"authorization": "Bearer x"}


def test_no_active_run_means_no_baggage(http_like: types.ModuleType) -> None:
    """With no active run, the call passes through unchanged (no baggage header added)."""
    install_run_id_baggage(["http_like.Client.request"])
    result = http_like.Client.request(url="u", headers={"authorization": "Bearer x"})
    assert "baggage" not in _headers(result)


def test_unresolved_target_warns_not_silent() -> None:
    """A non-importable target is reported as unresolved (named), never a silent no-op."""
    report = install_run_id_baggage(["nope.NotReal.request"])
    assert "nope.NotReal.request" in report.unresolved
    assert report.installed == ()


def test_host_error_is_not_swallowed(http_like: types.ModuleType) -> None:
    """If the wrapped call raises, the error propagates (the producer never hides it)."""

    def boom(**_kwargs: object) -> None:
        raise RuntimeError("network down")

    http_like.Client.boom = staticmethod(boom)
    install_run_id_baggage(["http_like.Client.boom"])
    token = active_run_id.set(RunId("run-7"))
    try:
        with pytest.raises(RuntimeError, match="network down"):
            http_like.Client.boom(url="u")
    finally:
        active_run_id.reset(token)


def test_installed_targets_reported(http_like: types.ModuleType) -> None:
    """A resolved target is reported as installed."""
    report = install_run_id_baggage(["http_like.Client.request"])
    assert "http_like.Client.request" in report.installed
