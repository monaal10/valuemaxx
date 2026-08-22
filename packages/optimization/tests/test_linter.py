from __future__ import annotations

from uuid import UUID

from valuemaxx.core import TenantId
from valuemaxx.core.optimization import LinterFindingKind
from valuemaxx.optimization.linter import PromptBlock, TrafficCall, lint_traffic

TENANT = TenantId(UUID("11111111-1111-1111-1111-111111111111"))


def _call(call_id: str, run: str, body: str, volatile: str) -> TrafficCall:
    return TrafficCall(
        call_id=call_id,
        run_id=run,
        request_body=body,
        blocks=(
            PromptBlock(role="system", content="stable prefix"),
            PromptBlock(role="user", content=volatile),
            PromptBlock(role="system", content="a long stable suffix for caching"),
        ),
    )


def test_reports_cache_misalignment_as_a_structural_fact() -> None:
    findings = lint_traffic(
        tenant_id=TENANT,
        call_site_id="site",
        calls=(_call("1", "r1", "one", "A"), _call("2", "r2", "two", "B")),
    )
    cache = next(f for f in findings if f.kind is LinterFindingKind.CACHE_MISALIGNMENT)
    assert "stable" in cache.evidence.lower()
    assert "volatile" in cache.evidence.lower()


def test_exact_duplicates_are_only_reported_within_one_run() -> None:
    calls = (
        _call("1", "r1", '{"same":true}', "A"),
        _call("2", "r1", '{"same":true}', "A"),
        _call("3", "r2", '{"same":true}', "A"),
    )
    findings = lint_traffic(tenant_id=TENANT, call_site_id="site", calls=calls)
    duplicates = [f for f in findings if f.kind is LinterFindingKind.DUPLICATE_CALL]
    assert len(duplicates) == 1
    assert "r1" in duplicates[0].evidence


def test_semantically_equal_but_not_exact_bodies_are_not_duplicates() -> None:
    calls = (
        _call("1", "r1", '{"a":1,"b":2}', "A"),
        _call("2", "r1", '{ "b": 2, "a": 1 }', "A"),
    )
    findings = lint_traffic(tenant_id=TENANT, call_site_id="site", calls=calls)
    assert all(f.kind is not LinterFindingKind.DUPLICATE_CALL for f in findings)
