"""valuemaxx.onboarding — the onboarding agent (G2-ONBOARDING).

Reads a user's codebase and proposes/writes their outcome config:
scan → propose → suggest → validate → render → diff → dry-run → reviewable PR.
Depends only on ``valuemaxx.core`` ABCs/Protocols and ``valuemaxx.capabilities`` —
never a concrete store/surface/sibling logic package. The agent emits a diff, not
the codebase, and never echoes a secret into a proposal, diff, or log.

``register(registry)`` is the package's push-registration entry point (H6): it adds
the five onboarding capabilities to a registry.
"""

from __future__ import annotations

from valuemaxx.onboarding.service import OnboardingService, register

__all__ = ["OnboardingService", "register"]
