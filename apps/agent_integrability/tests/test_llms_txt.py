"""llms.txt generation tests — lists every capability + corrects model priors.

``generate_llms_txt`` produces an ``llms.txt`` from the registry: it lists EVERY
capability (name, surfaces, mode, description) plus an ``instructions`` section that
corrects the priors an LLM agent is likely to hold — binding tier is system-owned,
signal_class is system-mapped, and an attribution rule should be drafted via
``suggest_attribution_rule`` rather than guessed.
"""

from __future__ import annotations

from valuemaxx.agent_integrability.discovery import build_default_registry
from valuemaxx.agent_integrability.llms_txt import generate_llms_txt


def test_llms_txt_lists_every_capability() -> None:
    """Every capability name in the registry appears in the generated llms.txt."""
    registry = build_default_registry()
    text = generate_llms_txt(registry)
    for cap in registry.all():
        assert cap.name in text, f"{cap.name} missing from llms.txt"


def test_llms_txt_has_instructions_section_asserting_system_owned_axes() -> None:
    """The instructions section corrects model priors about the system-owned axes."""
    text = generate_llms_txt(build_default_registry())
    lowered = text.lower()
    assert "instructions" in lowered
    # binding tier is system-owned, signal_class is system-mapped
    assert "binding tier" in lowered
    assert "system-owned" in lowered
    assert "signal_class" in lowered
    assert "system-mapped" in lowered
    # use suggest_attribution_rule rather than guessing
    assert "suggest_attribution_rule" in text


def test_llms_txt_records_each_capabilitys_surfaces_and_mode() -> None:
    """Each capability line carries its surfaces and mode (so an agent picks the right one)."""
    registry = build_default_registry()
    text = generate_llms_txt(registry)
    # spot-check a known capability's mode is present
    assert "webhook_inbound" in text
    assert "async_job" in text
    assert "request_response" in text


def test_llms_txt_is_deterministic() -> None:
    """Generating twice over the same registry yields identical text."""
    registry = build_default_registry()
    assert generate_llms_txt(registry) == generate_llms_txt(registry)
