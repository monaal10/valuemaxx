"""shared_costs.yaml intake — the Tier-2/Tier-3 declared-key config (§5.4)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from valuemaxx.allocation.config import (
    SharedCostInput,
    SharedCostsConfig,
    load_shared_costs,
)
from valuemaxx.core import TenantId

TENANT = TenantId(UUID("00000000-0000-0000-0000-0000000000c1"))

_YAML = """
shared_costs:
  - name: vector-db
    amount_usd: "300.00"
    tier: shared_proportional
    allocation_key: requests
    rule_version: v1
  - name: idle-gpu-pool
    amount_usd: "1000.00"
    tier: fixed_overhead
    is_idle_gpu: true
  - name: platform-license
    amount_usd: "200.00"
    tier: fixed_overhead
    is_idle_gpu: false
"""


def test_loads_shared_cost_inputs() -> None:
    """A populated yaml parses into typed SharedCostInput entries."""
    config = load_shared_costs(_YAML, tenant_id=TENANT)
    assert isinstance(config, SharedCostsConfig)
    assert len(config.inputs) == 3
    first = config.inputs[0]
    assert isinstance(first, SharedCostInput)
    assert first.name == "vector-db"
    assert first.amount_usd == Decimal("300.00")
    assert first.allocation_key == "requests"


def test_amounts_are_decimal_not_float() -> None:
    """Shared-cost amounts are exact Decimal, never float."""
    config = load_shared_costs(_YAML, tenant_id=TENANT)
    assert all(isinstance(i.amount_usd, Decimal) for i in config.inputs)


def test_idle_gpu_flag_parsed() -> None:
    """The is_idle_gpu flag is parsed for fixed-overhead inputs."""
    config = load_shared_costs(_YAML, tenant_id=TENANT)
    idle = next(i for i in config.inputs if i.name == "idle-gpu-pool")
    license_ = next(i for i in config.inputs if i.name == "platform-license")
    assert idle.is_idle_gpu is True
    assert license_.is_idle_gpu is False


def test_absent_config_is_tier1_only_mode() -> None:
    """Absent / empty yaml yields an empty config (Tier-1-only mode, §5.4)."""
    config = load_shared_costs("", tenant_id=TENANT)
    assert config.inputs == ()
    assert config.is_tier1_only is True


def test_none_text_is_tier1_only() -> None:
    """A yaml that parses to None (blank doc) is Tier-1-only, not an error."""
    config = load_shared_costs("\n\n", tenant_id=TENANT)
    assert config.is_tier1_only is True


def test_shared_proportional_requires_allocation_key() -> None:
    """A shared_proportional input without an allocation_key is rejected."""
    bad = """
shared_costs:
  - name: x
    amount_usd: "1.0"
    tier: shared_proportional
"""
    with pytest.raises(ValueError, match="allocation_key"):
        load_shared_costs(bad, tenant_id=TENANT)


def test_unknown_tier_rejected() -> None:
    """An input declaring an unknown tier is rejected at the boundary."""
    bad = """
shared_costs:
  - name: x
    amount_usd: "1.0"
    tier: bogus
"""
    with pytest.raises(ValueError, match="unknown allocation tier"):
        load_shared_costs(bad, tenant_id=TENANT)


def test_inputs_for_tier_filters() -> None:
    """inputs_for_tier returns only the inputs of the requested tier."""
    from valuemaxx.core import AllocationTier

    config = load_shared_costs(_YAML, tenant_id=TENANT)
    fixed = config.inputs_for_tier(AllocationTier.FIXED_OVERHEAD)
    assert {i.name for i in fixed} == {"idle-gpu-pool", "platform-license"}


def test_non_mapping_yaml_rejected() -> None:
    """A top-level yaml that is not a mapping is rejected."""
    with pytest.raises(ValueError, match="must be a mapping"):
        load_shared_costs("- just\n- a\n- list\n", tenant_id=TENANT)


def test_shared_costs_not_a_list_rejected() -> None:
    """A 'shared_costs' value that is not a list is rejected."""
    with pytest.raises(ValueError, match="must be a list"):
        load_shared_costs("shared_costs: 5\n", tenant_id=TENANT)


def test_entry_not_a_mapping_rejected() -> None:
    """A shared_costs entry that is not a mapping is rejected."""
    with pytest.raises(ValueError, match="must be a mapping"):
        load_shared_costs("shared_costs:\n  - just-a-string\n", tenant_id=TENANT)


def test_entry_without_tier_rejected() -> None:
    """A shared_costs entry without a string tier is rejected."""
    bad = "shared_costs:\n  - name: x\n    amount_usd: '1'\n"
    with pytest.raises(ValueError, match="string 'tier'"):
        load_shared_costs(bad, tenant_id=TENANT)


def test_bad_amount_rejected() -> None:
    """A non-decimal amount is rejected with a typed message."""
    bad = "shared_costs:\n  - name: x\n    amount_usd: not-a-number\n    tier: fixed_overhead\n"
    with pytest.raises(ValueError, match="not a valid decimal"):
        load_shared_costs(bad, tenant_id=TENANT)


def test_amount_wrong_type_rejected() -> None:
    """An amount that is neither string nor int (e.g. a list) is rejected."""
    bad = "shared_costs:\n  - name: x\n    amount_usd: [1, 2]\n    tier: fixed_overhead\n"
    with pytest.raises(ValueError, match="decimal string or integer"):
        load_shared_costs(bad, tenant_id=TENANT)


def test_integer_amount_coerced_to_decimal() -> None:
    """An integer amount in yaml is coerced to exact Decimal."""
    one = "shared_costs:\n  - name: x\n    amount_usd: 42\n    tier: fixed_overhead\n"
    config = load_shared_costs(one, tenant_id=TENANT)
    assert config.inputs[0].amount_usd == Decimal("42")
