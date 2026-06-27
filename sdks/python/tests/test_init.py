"""SDK — ``init()`` is a one-line, fail-open producer (§5.1, H9).

``init()`` builds the config (only pydantic validation of the literal args may
raise), then runs every instrumentation step inside a fail-open guard so an
internal error NEVER propagates into the host. It returns an :class:`InitResult`
describing what took effect (patched?, granularity, warnings). Content (prompt/
response) is OFF by default (§9.1).
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from pydantic import SecretStr
from valuemaxx.core.ids import TenantId
from valuemaxx.sdk import InitConfig, InitResult, init


def _tenant() -> TenantId:
    return TenantId(uuid4())


def test_init_returns_result_and_never_raises() -> None:
    """test_init_returns_result_and_never_raises: a normal init returns an InitResult."""
    result = init(tenant_id=_tenant(), ingest_key="secret-key", endpoint="https://ingest.example")
    assert isinstance(result, InitResult)


def test_init_never_raises_into_host_when_a_step_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """test_init_never_raises_into_host_when_a_step_fails: an internal failure is swallowed."""

    def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("instrumentation blew up")

    # force the self-test step to raise; init must still return, never propagate
    monkeypatch.setattr("valuemaxx.sdk._bootstrap.version_selftest", _boom)
    result = init(tenant_id=_tenant(), ingest_key="k", endpoint="https://x.example")
    assert isinstance(result, InitResult)
    assert any("blew up" in w or "internal" in w.lower() for w in result.warnings)


def test_init_content_off_by_default() -> None:
    """test_init_content_off_by_default: capture_content defaults to False (§9.1)."""
    result = init(tenant_id=_tenant(), ingest_key="k", endpoint="https://x.example")
    assert result.effective.capture_content is False


def test_init_content_opt_in_respected() -> None:
    """test_init_content_opt_in_respected: explicit capture_content=True is honoured."""
    result = init(
        tenant_id=_tenant(),
        ingest_key="k",
        endpoint="https://x.example",
        capture_content=True,
    )
    assert result.effective.capture_content is True


def test_ingest_key_never_in_config_repr() -> None:
    """test_ingest_key_never_in_config_repr: the secret never appears in repr/str/dump."""
    config = InitConfig(
        tenant_id=_tenant(),
        ingest_key=SecretStr("super-secret-123"),
        endpoint="https://x.example",
    )
    assert "super-secret-123" not in repr(config)
    assert "super-secret-123" not in str(config)
    assert "super-secret-123" not in str(config.model_dump())


def test_ingest_key_never_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    """test_ingest_key_never_in_logs: init logs never leak the ingest key."""
    with caplog.at_level(logging.DEBUG):
        init(tenant_id=_tenant(), ingest_key="leak-me-please", endpoint="https://x.example")
    for record in caplog.records:
        assert "leak-me-please" not in record.getMessage()


def test_init_rejects_non_http_endpoint() -> None:
    """test_init_rejects_non_http_endpoint: a bad endpoint fails config validation (pre-guard)."""
    with pytest.raises(ValueError, match="http"):
        InitConfig(tenant_id=_tenant(), ingest_key=SecretStr("k"), endpoint="ftp://nope")


def test_self_test_warning_surfaces_on_result() -> None:
    """test_self_test_warning_surfaces_on_result: an incompatible version surfaces a warning."""
    result = init(
        tenant_id=_tenant(),
        ingest_key="k",
        endpoint="https://x.example",
        installed_versions={"httpx": "0.1.0"},  # far below the supported floor
    )
    assert any("httpx" in w and "0.1.0" in w for w in result.warnings)
    assert result.capture_granularity == "per_call"  # degraded, never silent
