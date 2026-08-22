from __future__ import annotations

from decimal import Decimal

from valuemaxx.core.optimization import OptimizationConfig
from valuemaxx.optimization.identity import compute_config_identity, infer_system_template


def test_rolling_lcs_removes_interpolated_slots() -> None:
    inferred = infer_system_template(
        (
            "You help Acme on the pro plan. Be concise.",
            "You help Globex on the free plan. Be concise.",
            "You help Initech on the team plan. Be concise.",
        )
    )
    assert "You help " in inferred.template
    assert "Be concise." in inferred.template
    assert inferred.strength > Decimal("0.3")
    assert inferred.weak is False


def test_dynamic_system_prompt_uses_explicit_structure_fallback() -> None:
    inferred = infer_system_template(("alpha", "98765", "ZZ!"), structure=("system", "user"))
    assert inferred.weak is True
    assert inferred.template == "structure:system|user"


def test_config_hashes_attribute_components_independently() -> None:
    config = OptimizationConfig(model="m", provider="p", max_tokens=100)
    first = compute_config_identity(
        system_messages=("You help Acme. Be brief.", "You help Globex. Be brief."),
        tools=({"name": "search", "description": "Find"},),
        config=config,
    )
    changed_params = compute_config_identity(
        system_messages=("You help Acme. Be brief.", "You help Globex. Be brief."),
        tools=({"name": "search", "description": "Find"},),
        config=config.model_copy(update={"max_tokens": 200}),
    )
    assert first.system_hash == changed_params.system_hash
    assert first.tools_hash == changed_params.tools_hash
    assert first.params_hash != changed_params.params_hash


def test_tool_hash_is_order_independent() -> None:
    config = OptimizationConfig(model="m", provider="p")
    a = compute_config_identity(
        system_messages=("stable",), tools=({"name": "b"}, {"name": "a"}), config=config
    )
    b = compute_config_identity(
        system_messages=("stable",), tools=({"name": "a"}, {"name": "b"}), config=config
    )
    assert a.tools_hash == b.tools_hash
