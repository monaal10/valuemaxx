"""The SDK's init config + result models (strict, secret-safe).

``InitConfig`` is frozen/extra-forbid/strict. ``ingest_key`` is a
:class:`~pydantic.SecretStr` so it never appears in ``repr``/``str``/``model_dump``
or any log (§9.1 / AGENTS.md §5b). ``capture_content`` is OFF by default — cost
capture needs only token counts + metadata (§9.1). ``fail_open`` is
``Literal[True]``: the SDK can never be *configured* to crash the host.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator
from valuemaxx.core.ids import TenantId


class InitConfig(BaseModel):
    """Validated, secret-safe configuration for :func:`valuemaxx.sdk.init`."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    tenant_id: TenantId
    ingest_key: SecretStr
    endpoint: str
    capture_content: bool = False
    service_name: str = "valuemaxx"
    max_queue_size: int = 10_000
    fail_open: Literal[True] = True

    @field_validator("endpoint")
    @classmethod
    def _endpoint_is_http(cls, value: str) -> str:
        """Reject a non-http(s) endpoint (telemetry only goes over http(s))."""
        if not value.startswith(("http://", "https://")):
            raise ValueError(f"endpoint must be http(s), got {value!r}")
        return value


class EffectiveConfig(BaseModel):
    """The non-secret config echo surfaced on the InitResult (never carries the key)."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    tenant_id: TenantId
    endpoint: str
    capture_content: bool
    service_name: str
    max_queue_size: int


__all__ = ["EffectiveConfig", "InitConfig"]
