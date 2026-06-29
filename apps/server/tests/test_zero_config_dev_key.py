"""Zero-config: `valuemaxx up` works with no ingest key configured.

A solo dev running locally has exactly one tenant — themselves — so making them
hand-craft ``VALUEMAXX_INGEST_KEYS={"dev-key": "<a-uuid-they-invent>"}`` before the
backend does anything is pure friction. When no ingest key is configured, the settings
synthesize a **deterministic** dev key -> dev tenant, so:

* the first run "just works" (ingest + query succeed with the printed dev key);
* it is STABLE across restarts (a fixed UUID), so data persisted under the dev tenant
  is still readable after a restart — never orphaned under a fresh random tenant;
* configuring real keys turns the dev fallback OFF entirely (production is unchanged).
"""

from __future__ import annotations

from uuid import UUID

from valuemaxx.server.settings import DEV_INGEST_KEY, DEV_TENANT_ID, ServerSettings


def test_no_keys_configured_yields_a_deterministic_dev_key() -> None:
    """With no ingest_keys, resolved_ingest_keys() is a single stable dev key -> dev tenant."""
    settings = ServerSettings(ingest_keys={})
    resolved = settings.resolved_ingest_keys()
    assert resolved == {DEV_INGEST_KEY: DEV_TENANT_ID}
    # the dev tenant is a valid UUID (tenancy is UUID-identified) and STABLE.
    assert UUID(DEV_TENANT_ID)
    assert ServerSettings(ingest_keys={}).resolved_ingest_keys() == resolved  # deterministic


def test_configured_keys_disable_the_dev_fallback() -> None:
    """When real keys are set, resolved_ingest_keys() returns exactly those — no dev key."""
    real = {"prod-key": "6f1c3b2a-0000-4a00-8000-000000000001"}
    settings = ServerSettings(ingest_keys=real)
    resolved = settings.resolved_ingest_keys()
    assert resolved == real
    assert DEV_INGEST_KEY not in resolved  # the dev fallback is OFF once configured


def test_is_using_dev_fallback_flag() -> None:
    """A flag tells the CLI whether to print the generated dev key (only when synthesized)."""
    assert ServerSettings(ingest_keys={}).is_using_dev_fallback() is True
    assert (
        ServerSettings(
            ingest_keys={"k": "6f1c3b2a-0000-4a00-8000-000000000001"}
        ).is_using_dev_fallback()
        is False
    )
