---
name: valuemaxx-integration
description: >-
  Wire valuemaxx (AI margin intelligence — cost-per-outcome with confidence) into a
  codebase. Use when adding cost capture, defining outcomes, or measuring
  cost-per-outcome for an AI agent app. Scans the repo, proposes outcomes, validates
  them, and hands off a reviewable diff — never auto-applies a rule.
---

# valuemaxx integration Skill

valuemaxx measures **cost-per-outcome with confidence**. Surfaces (API/MCP/CLI/notify)
are thin projections of one capability registry; everything below is driven through
those capabilities. The flow is **scan → propose → wire → validate → hand-off as a
diff**.

## Honesty invariants (do NOT violate)

The three axes are **system-owned** — never set or guess them:

- **Binding tier** (`exact | deterministic | candidate | likely`) is system-owned. An
  inferred match is never `exact`. `candidate`/`likely` are advisory, never
  billing-grade.
- **signal_class** (`action_attempted | outcome_confirmed | outcome_retracted`) is
  **system-mapped** from the outcome source. A successful tool call is
  `action_attempted` unless the result is authoritative.
- **Cost provenance** is system-owned; an estimate is never rendered as billed.

Every rollup carries `minimum_tier` + `confidence_distribution` — never collapse them.

## Steps

1. **Scan** the codebase for run boundaries (where `valuemaxx.init()` goes) and
   candidate outcome sites (status setters, ORM saves, outbound Stripe/CRM/email
   calls, webhook handlers). Use the `scan_codebase` capability.
2. **Propose** outcomes with `propose_onboarding_diff` (or draft a single rule with
   `scaffold_outcome_rule`). Every proposal is an **UNCONFIRMED candidate**.
3. **Wire** the SDK init — add `valuemaxx.init()` at the app entrypoint. Validate the
   snippet with `validate_init`.
4. **Validate** the `outcomes.yaml` with `validate_outcome_rule` (the safe-predicate
   allowlist — no `eval`, no dunder access).
5. **Suggest** an attribution rule with `suggest_attribution_rule` — it returns an
   UNCONFIRMED candidate. Do **not** hand-write or auto-apply a rule.
6. **Hand off** the change as a reviewable diff (hunks only). A human confirms; the
   system never auto-applies.

See the generated `llms.txt` for the full capability list, and `examples/` for
per-framework starting points (fastapi+langchain, openai, anthropic). Each example
ships a runnable snippet plus a validating `outcomes.yaml`.
