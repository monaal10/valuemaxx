## 2. CANONICAL `atm_` PACKAGE NAMING

| Layer | Distribution name | Import package | Path |
|---|---|---|---|
| core | `atm-core` | `atm_core` | `packages/core/` |
| capabilities | `atm-capabilities` | `atm_capabilities` | `packages/capabilities/` |
| capture | `atm-capture` | `atm_capture` | `packages/capture/` |
| outcomes | `atm-outcomes` | `atm_outcomes` | `packages/outcomes/` |
| attribution | `atm-attribution` | `atm_attribution` | `packages/attribution/` |
| reconciliation | `atm-reconciliation` | `atm_reconciliation` | `packages/reconciliation/` |
| allocation | `atm-allocation` | `atm_allocation` | `packages/allocation/` |
| metrics | `atm-metrics` | `atm_metrics` | `packages/metrics/` |
| eval | `atm-eval` | `atm_eval` | `packages/eval/` |
| onboarding | `atm-onboarding` | `atm_onboarding` | `packages/onboarding/` |
| store | `atm-store` | `atm_store` | `packages/store/` |
| api app | `atm-api` | `atm_api` | `apps/api/` |
| mcp app | `atm-mcp` | `atm_mcp` | `apps/mcp/` |
| cli app | `atm-cli` | `atm_cli` | `apps/cli/` |
| notify app | `atm-notify` | `atm_notify` | `apps/notify/` |
| agent-integrability | `atm-agent-integrability` | `atm_agent_integrability` | `apps/agent_integrability/` |
| python SDK | `atm-margin` | `atm_margin` | `sdks/python/` |
| TS SDK | `@atm-margin/sdk` | (n/a) | `sdks/typescript/` |

**Rules:** every package's `src` top-dir matches `^atm_[a-z]+$`. The 9 logic packages (`atm_capture, atm_outcomes, atm_attribution, atm_reconciliation, atm_allocation, atm_metrics, atm_eval, atm_onboarding, atm_store`) are mutually independent — cross-package needs go through `atm_core` ABCs/Protocols. `atm_capabilities` imports only stdlib + pydantic + typing.

---

## 3. CONFORMANCE RULE LIST (split static/ + behavioral/ per H4)

The harness lives at `tests/conformance/{static,behavioral}/`. Each rule is authored RED with BOTH a negative fixture (a synthetic violation it must flag) AND the foundation-passing assertion. Foundation rules go green immediately against F0-CORE/F0-CAPS; the rest stay red (skip-marked with the owning task ID, never silently xfailed) until their owning package turns them green.

### `static/` (AST / import-graph; no runtime)

| Rule | Meaning | Turned green by |
|---|---|---|
| `no_type_outside_core` | no domain type defined outside `atm_core` (config-AST models on a fixed allowlist) | foundation + each G2 pkg |
| `no_logic_to_surface_import` | logic pkgs never import fastapi/typer/mcp/`apps.*` | EVAL, ONBOARDING |
| `dependency_direction` | deps flow toward `core`; no logic→logic | foundation |
| `no_tiktoken_for_cost` | no tokenizer import in cost paths | CAPTURE, EVAL |
| `tenant_scoping` | every repo query path takes `tenant_id` first | STORE |
| `additive_reconciliation` | recon repo has no update/mutate-estimate path | STORE, RECON |
| `migration_no_autogen_drift` | alembic autogenerate yields empty diff | STORE |
| `wire_semconv_parity` | Py/TS OTLP key-sets byte-identical | CAPTURE (Py), OTLP-CONTRACT |
| `granularity_labeled` | every CostEvent carries `capture_granularity` | CAPTURE |
| `streaming_no_delta_sum` | streaming output overwrites terminal, never sums | CAPTURE |
| `resolver_emits_only_its_own_tier` | a resolver's candidates all carry its tier | ATTRIBUTION |
| `candidate_likely_never_billing_grade` | candidate/likely always review-required, never billing-grade | ATTRIBUTION |
| `no_user_override_of_confidence_mapping` | tier→label map is system-owned, no setter | ATTRIBUTION |
| `grade_cap_invariant` | reliable only off outcome_label-on-valid-task / human≥50 @ TPR/TNR≥0.9 | EVAL |
| `no_auto_switch` | recommendation never auto-applies (`auto_switch: Literal[False]`) | EVAL |
| `two_phase_gate_ordered` | phase-2 cost gate only after phase-1 approved | EVAL |
| `smoke_no_ci_confirm_requires_ci` | smoke eliminates >25% w/o CI; confirm needs 95% CI separation | EVAL |
| `no_eval_in_predicate` | no eval/exec/dunder in predicates or metric DSL | OUTCOMES, METRICS, ONBOARDING |
| `no_raw_source_exfil` | onboarding/github emits diffs not whole files; no off-box raw-source path | ONBOARDING |
| `notify_aggregate_only` | digest models hold no raw/PII fields | NOTIFY |
| `honesty_provenance_set` (M1) | every cost-bearing field carries a `ProvenanceLabel` | foundation |
| `signal_class_never_user_set` (M1) | no user path writes `signal_class`; system `map_signal` only | OUTCOMES, ONBOARDING |
| `rollup_carries_confidence` | every rollup-shaped model carries both H7 fields | foundation + ALLOC, METRICS, ONBOARDING dry-run |
| `capability_on_every_declared_surface` | each capability appears on every surface it declares | G4 apps |

### `behavioral/` (RUNTIME, sentinel-driven; H4)

| Rule | Meaning | Turned green by |
|---|---|---|
| `no_secret_logging` | inject a sentinel ingest/provider key, exercise paths, assert it appears in NO span attribute, NO log record, NO DB row (runtime, not static grep) | OUTCOMES, RECON, EVAL, ONBOARDING; final at G5 |
| `sdk_fails_open` | injected throwing client doesn't break host; our exceptions suppressed+counted | CAPTURE |
| `honesty_axes_invariants` | constructing illegal states (estimate-as-billed, inferred-as-exact, attempt-as-confirmed) each raises | foundation |

**The three honesty axes are `Provenance`, `BindingTier`, `SignalClass` — the ONLY system axes.** `EvalGrade` and `ReconciliationState` are deliberately local/display, never axes (asserted by a G1-EXIT meta-test).

---

## 4. TASK ENTRIES (inlined, self-contained)

> Cross-cutting rules every task honors: TDD red→green→refactor (watch each test fail first); `pyright --strict` + ruff clean before commit; money is `Decimal` with `ROUND_HALF_EVEN` (M7), never `float`; `tenant_id` structurally required (no anonymous events, no untenanted queries); every rollup carries both H7 fields and `minimum_tier` == least-trusted present tier; inject `Clock`/`UuidGen`/`Rng` (no `datetime.now()`/`uuid4()`/`random()` in app code); every G2 package ends with `register(registry)` (M10); each public function/class needs an accurate docstring.

---

### GROUP 0 — FOUNDATION (serial, first, alone)

#### [F0-TOOLING] — workspace, gates, CI, empty skeletons
**package:** tooling (repo root) · **group:** G0 · **depends-on:** none

**File tree this task creates:**
```
antitokenmaxxing/
├── pyproject.toml                 # root uv workspace
├── uv.lock
├── ruff.toml
├── pyrightconfig.json
├── .importlinter
├── .coveragerc
├── .github/workflows/ci.yml
├── packages/
│   ├── core/          { pyproject.toml, py.typed, src/atm_core/__init__.py, tests/__init__.py }
│   ├── capabilities/  { pyproject.toml, py.typed, src/atm_capabilities/__init__.py, tests/__init__.py }
│   ├── capture/       { …/atm_capture/__init__.py … }
│   ├── outcomes/      { …/atm_outcomes/__init__.py … }
│   ├── attribution/   { …/atm_attribution/__init__.py … }
│   ├── reconciliation/{ …/atm_reconciliation/__init__.py … }
│   ├── allocation/    { …/atm_allocation/__init__.py … }
│   ├── metrics/       { …/atm_metrics/__init__.py … }
│   ├── eval/          { …/atm_eval/__init__.py … }
│   ├── onboarding/    { …/atm_onboarding/__init__.py … }
│   └── store/         { …/atm_store/__init__.py … }
├── apps/   { api, mcp, cli, notify, agent_integrability } (empty atm_* skeletons)
├── sdks/   { python, typescript } (skeleton only; built G3)
└── tests/conformance/   { __init__.py }
```

Each `packages/*/pyproject.toml` declares `name = "atm-<pkg>"`, `[tool.hatch.build]` packages the `src/atm_<pkg>` dir, ships `py.typed`. Workspace members listed under `[tool.uv.workspace] members`.

**`ruff.toml`:** `select` includes `E,F,I,UP,B,ANN,TID,RUF`. **Banned-API for `tiktoken`:** `[tool.ruff.lint.flake8-tidy-imports.banned-api]` → `"tiktoken" = { msg = "tiktoken banned for cost (undercounts Claude ~12%); flagged-fallback path only — see AGENTS §5b" }`; the one allowed fallback gets `# noqa: TID251` with reason+issue link. `flake8-annotations`: forbid `Any` in public signatures.

**`pyrightconfig.json`:** `"typeCheckingMode":"strict"`, `"reportUnnecessaryTypeIgnoreComment":"error"`, `"reportMissingTypeStubs":"error"`, all packages on `include`.

**`.importlinter` contracts:** Layered top→bottom `apps` → `capabilities`+logic → `core` (core lowest, imports nothing internal). Forbidden: logic packages may not import fastapi/typer/mcp/`apps.*`. Independence: the 9 logic packages mutually independent; cross-package via `atm_core` ABCs/Protocols.

**`.coveragerc`/pytest-cov:** `fail_under = 90`, branch on. Omit: `apps/*` projections, `clients/*` generated, `**/__init__.py` pure re-exports.

**`ci.yml` jobs:** `uv sync` → `ruff check`+`ruff format --check` → `pyright` → `lint-imports` → `pytest` (coverage gate) → conformance suite. Includes the H3 semconv regen+`git diff --exit-code` step (stub now, wired at G2-CAPTURE/OTLP-CONTRACT).

**TDD-first tests:** `test_uv_sync_resolves` (subprocess `uv sync` exit 0; each member importable); `test_pyright_strict_clean`; `test_ruff_clean`; `test_import_linter_contracts_pass`; `test_coverage_gate_is_90` (`fail_under==90` and `branch=true`); `test_no_foreign_prefix` (walk `packages/*/src`; no `ai_margin_*`/`atmx_*`; every top-dir `^atm_[a-z]+$`).

**Definition of Done:** `uv sync` exits 0 and lockfile resolves; pyright/ruff/lint-imports exit 0 on empty skeletons; coverage gate configured to 90; `atm_` prefix locked by test; CI file present with all jobs (some red until later groups).

---

#### [F0-CORE-1a] — core primitives: enums, ids, base, token vector, provenance, errors
**package:** packages/core · **group:** G0 · **depends-on:** F0-TOOLING

**File tree:** `packages/core/src/atm_core/{enums.py, ids.py, base.py, tokens.py, provenance.py, errors.py}`

**`enums.py`** (all `StrEnum`, exact values):
```python
from enum import StrEnum
class Provenance(StrEnum):
    MEASURED="measured"; ESTIMATED="estimated"; ALLOCATED="allocated"
    PROVIDER_RECONCILED="provider_reconciled"; MANUAL_RECONCILED="manual_reconciled"
class BindingTier(StrEnum):
    EXACT="exact"; DETERMINISTIC="deterministic"; CANDIDATE="candidate"; LIKELY="likely"
class SignalClass(StrEnum):
    ACTION_ATTEMPTED="action_attempted"; OUTCOME_CONFIRMED="outcome_confirmed"; OUTCOME_RETRACTED="outcome_retracted"
class CaptureGranularity(StrEnum):
    PER_ATTEMPT="per_attempt"; PER_CALL="per_call"
class ConfidenceLabel(StrEnum):        # §3.1 composed user-facing label
    HIGH="high"; MEDIUM="medium"; LOW="low"; ADVISORY="advisory"
class AllocationTier(StrEnum):         # §5.4
    DIRECT="direct"; SHARED_PROPORTIONAL="shared_proportional"; FIXED_OVERHEAD="fixed_overhead"
class ReconciliationState(StrEnum):    # DISPLAY state on aggregates, NOT a Provenance value (§5.3a)
    PROVIDER_RECONCILED="provider_reconciled"; PROVISIONAL="provisional"; ESTIMATE_ONLY="estimate_only"
class EvalGrade(StrEnum):              # local to eval — NOT a system axis
    RELIABLE="reliable"; DIRECTIONAL="directional"
class LabelSource(StrEnum):            # §8.2 ground-truth rungs, ranked
    OUTCOME_LABEL="outcome_label"; HUMAN_LABELED="human_labeled"; LLM_JUDGE="llm_judge"; REFERENCE="reference"
class TokenClass(StrEnum):             # §5.2 six classes
    INPUT_UNCACHED="input_uncached"; CACHE_READ="cache_read"; CACHE_WRITE_5M="cache_write_5m"
    CACHE_WRITE_1H="cache_write_1h"; OUTPUT="output"; REASONING="reasoning"
```
Comments-and-tests MUST encode: `ReconciliationState`/`EvalGrade` are NOT honesty axes; only `Provenance`/`BindingTier`/`SignalClass` are.

**`ids.py`:** `TenantId=NewType("TenantId",UUID)`; `RunId, CostEventId, OutcomeEventId, AttributionId, ReconciliationRecordId, AttemptId, CorrelationId` as `NewType(str)`.

**`base.py`:**
```python
class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
class TenantScopedModel(StrictModel):
    tenant_id: TenantId          # REQUIRED, no default — untenanted construction raises
    @field_validator("*", mode="before")
    @classmethod
    def _reject_naive_datetimes(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            raise ValueError("naive datetime forbidden; supply tz-aware UTC")
        return v
```

**`tokens.py` — `TokenVector` with the six enforced invariants (§5.2):** fields `input_uncached, cache_read, cache_write_5m, cache_write_1h, output, reasoning: int` (reasoning DERIVED, embedded within output). `@model_validator(after)` enforces non-negative + `reasoning <= output`. `total_input` property = sum of four input classes. `from_provider(...)` additionally guards `cache_read+cache_write_5m+cache_write_1h <= total_input`. The six invariants (each a test): (1) all non-negative; (2) `output ⊇ reasoning`; (3) cache ≤ total_input; (4) 5m/1h are distinct fields (never one flat `cache_write`); (5) `from_provider` rejects (3) violation; (6) reasoning derived/separate, never double-added into input side.

**`provenance.py` — `ProvenanceLabel`:** `provenance: Provenance`, `reconciliation_record_id: str|None=None`, `note: str|None=None`. `@model_validator(after)` link rules: reconciled (`PROVIDER_RECONCILED`/`MANUAL_RECONCILED`) requires `reconciliation_record_id`; non-reconciled must not carry one.

**`errors.py`:** `AtmError(Exception)`; `TenantScopeError`, `ProvenanceWarning`, `HonestyInvariantError`, `CaptureError`, `BindingAmbiguityError` (all subclass `AtmError`). No bare exceptions downstream.

**TDD-first tests:** T-EN-1 `test_provenance_values_exact`; T-EN-2 `test_binding_tier_and_signal_values_exact`; T-EN-3 `test_reconciliation_state_not_a_provenance` (`provisional`/`estimate_only` not in Provenance set); T-BASE-1 `test_tenant_required`; T-BASE-2 `test_naive_datetime_rejected`; T-BASE-3 `test_frozen_forbid_strict` (mutate raises, extra raises, `"5"`→int strict raises); T-TV-1..6 (negative rejected; reasoning≤output; cache≤total via `from_provider`; 5m/1h distinct round-trip; `total_input` property; hypothesis round-trip); T-PL-1/2 (reconciled requires id; unreconciled forbids id).

**Definition of Done:** enum string values match design tables exactly; `TenantScopedModel` rejects missing/None tenant and naive datetimes; frozen+forbid+strict enforced; `TokenVector` enforces all six invariants + `from_provider` guard; `ProvenanceLabel` link rules hold both directions; pyright/ruff clean.

---

#### [F0-CORE-1b] — domain event + rollup models (incl. the H7 propagation heart)
**package:** packages/core · **group:** G0 · **depends-on:** F0-CORE-1a

**File tree:** `packages/core/src/atm_core/{cost.py, outcome.py, run.py, attribution.py, reconciliation.py, allocation.py, metrics.py, rollup.py}`

**`cost.py` — `CostEvent`** (one HTTP attempt, `TenantScopedModel`): `id: CostEventId`, `run_id: RunId`, `attempt_id: AttemptId`, `provider: str`, `model: str`, `tokens: TokenVector`, `capture_granularity: CaptureGranularity`, `provenance: ProvenanceLabel`, `cost_usd: Decimal|None` (None when PTU/billing-uncertain per H10 — never fabricated), `is_streaming: bool`, `partial_recovered: bool`, `billing_uncertain_abort: bool`, `provenance_warnings: tuple[str,...]`, `occurred_at: datetime`. Property `idempotency_key -> (run_id, attempt_id)` (M7 dedup). Money is `Decimal`, ROUND_HALF_EVEN at compute sites.

**`outcome.py` — `OutcomeBinding`** (`run_id, tier, bound_by` all nullable until bound) **+ `OutcomeEvent`** (`TenantScopedModel`): `id, name, signal_class, value: Decimal|None, occurred_at, binding, entity_keys: frozenset[tuple[str,str]], correlation_id: CorrelationId|None, source, raw: Mapping[str,object]`. Property `idempotency_key = correlation_id or (source, id)`.

**`run.py` — `Run`:** `id, agent_name: str|None, started_at, ended_at: datetime|None, entity_keys`.

**`attribution.py` — `AttributionCandidate`** (`run_id, tier, score, rationale`) **+ `AttributionResult`** (`outcome_id, run_id|None, tier|None, bound_by|None, candidates, review_required`). Property `is_billing_grade = tier in (EXACT, DETERMINISTIC)` — candidate/likely NEVER billing-grade.

**`reconciliation.py` — `ReconciliationRecord`** (additive, never UPDATE): `id, match_key: tuple[str,str,str,str,str]` = (provider,project,model,token_class,day), `estimated_total, billed_total, proration_factor, drift_pct: Decimal`, `drift_cause_ranked: tuple[str,...]`, `created_at`. No field points back to mutate an estimate.

**`allocation.py` — `AllocatedLine`:** `tier: AllocationTier`, `label: Provenance` (MEASURED for DIRECT; ALLOCATED for SHARED/FIXED), `amount_usd: Decimal`, `allocation_key: str|None`, `confidence: ConfidenceLabel`, `sensitivity_pct: Decimal|None`, `rule_version: str|None`, `quarantined: bool` (True iff FIXED_OVERHEAD). `@model_validator(after)` consistency: DIRECT⇒measured; shared/fixed⇒allocated; shared_proportional requires allocation_key; quarantined iff FIXED_OVERHEAD.

**`metrics.py` — `MetricDefinition`** (typed shape; full grammar at G2-METRICS): `name, numerator: str` (allowlisted), `denominator: str` (retracted excluded), `filters, group_by`.

**`rollup.py` — the H7 heart:**
```python
_TIER_ORDER = (LIKELY, CANDIDATE, DETERMINISTIC, EXACT)  # least→most trusted
class RollupConfidence(StrictModel):
    minimum_tier: BindingTier                            # least-trusted MEMBER tier (headline)
    confidence_distribution: Mapping[BindingTier, int]   # both required, both serialized
    @model_validator(mode="after")                       # M8: mode=after
    def _distribution_consistency(self):
        present = {t for t,n in self.confidence_distribution.items() if n>0}
        if not present: raise ValueError("...")
        if self.minimum_tier != min(present, key=_TIER_ORDER.index): raise ValueError("...")
        return self
    @classmethod
    def propagate(cls, tiers): ...   # count + minimum_tier = least-trusted present
def compose_label(*, provenances, tiers, signals, eval_grade=None) -> ConfidenceLabel: ...
class RunCostRollup(TenantScopedModel):
    run_id; total_cost_usd: Decimal; by_token_class: Mapping[TokenClass,Decimal]
    provenance_breakdown: Mapping[Provenance,Decimal]; confidence: RollupConfidence
```
`compose_label` (§3.1): all-best→HIGH; any estimated/likely/directional→LOW; mixed candidate/allocated→MEDIUM.

**TDD-first tests:** T-CE-1/2 (idempotency key; `cost_usd=None` for PTU); T-OE-1/2 (correlation-id preferred; signal_class required); T-BND-1 (unbound allows None); T-AR-1 (`is_billing_grade` exact/deterministic only); T-RR-1/2 (additive — AST scan asserts no update-estimate field; proration/drift present); T-AL-1/2/3 (direct⇒measured; shared requires key; quarantined iff fixed); T-MD-1 (round-trip); **T-PROP-1..7 (the H7 heart, hypothesis):** minimum_tier = least-trusted; distribution counts == len(input); `[EXACT]+[CANDIDATE]*50` → minimum_tier==CANDIDATE and both shown (cannot look clean); aggregation never raises confidence; validator rejects `minimum_tier=EXACT, dist={CANDIDATE:3}`; both fields round-trip via `model_dump_json`; `compose_label` takes minimum.

**Definition of Done:** idempotency keys correct; `is_billing_grade` true only for exact/deterministic; `ReconciliationRecord` additive (no mutate field); `AllocatedLine` consistency holds; `RollupConfidence.minimum_tier == least-trusted present tier`; both H7 fields serialize+round-trip; pyright/ruff clean.

---

#### [F0-CORE-1c] — repository ABCs (tenant_id first on every method)
**package:** packages/core · **group:** G0 · **depends-on:** F0-CORE-1a

**File:** `packages/core/src/atm_core/repositories.py` (+ Protocol stubs for C3 interfaces named here, bodies at G1: `OutcomesPredicateValidator`, `SignalClassMapper`, `ReviewQueue`). Every `@abstractmethod` takes `tenant_id: TenantId` as **mandatory first parameter** (§3.2). Reconciliation repo is **append-only** (no `update`).

ABCs: `RunRepository` (upsert/get/list_by_entity), `CostEventRepository` (upsert M7 upsert-on-conflict / list_for_run / list_in_window), `OutcomeEventRepository` (upsert/get/`retract` confirmed→retracted only/list_unbound), `AttributionResultRepository` (upsert/get_for_outcome), `ReconciliationRepository` (`append`/list_for_match_key — NO update by design), `AllocationRepository` (upsert_lines/list_for_run), `RawRecordRepository` (put/get/`erase_by_entity` GDPR — H10).

**TDD-first tests:** T-REPO-1 `test_every_repo_method_tenant_id_first` (inspect.signature; first param after self is `tenant_id: TenantId`); T-REPO-2 `test_reconciliation_repo_is_append_only`; T-REPO-3 `test_outcome_repo_has_retract` + list_unbound; T-REPO-4 `test_raw_repo_has_erase_by_entity`; T-REPO-5 `test_all_seven_abcs_exported`.

**Definition of Done:** AST self-check passes (every abstractmethod tenant_id-first; recon has no update/replace/mutate; all 7 ABCs present and importable); pyright/ruff clean.

---

#### [F0-CORE-INIT] — explicit public surface
**package:** packages/core · **group:** G0 · **depends-on:** F0-CORE-1b, F0-CORE-1c

`packages/core/src/atm_core/__init__.py` with explicit `__all__` re-exporting every enum, id type, model, ABC, rollup helper. No wildcard.

**TDD:** `test_public_surface_complete` (everything from 1a/1b/1c importable from `atm_core` and in `__all__`); `test_no_wildcard_exports`.

**Definition of Done:** full core suite green; pyright strict clean; ruff clean; ≥90% line+branch on `atm_core`; `__all__` explicit and complete.

---

#### [F0-CAPS] — capability registry (single source of truth contract)
**package:** packages/capabilities · **group:** G0 · **depends-on:** F0-TOOLING

**Dependency law (H6/§3.2):** `atm_capabilities` imports only stdlib + pydantic + typing; no logic package, not even `atm_core` domain models (it is generic; capabilities carry their own pydantic I/O models). Conformance asserts import set ⊆ {stdlib, pydantic, typing}.

**File tree:** `packages/capabilities/src/atm_capabilities/{surfaces.py, decorator.py, registry.py, discovery.py, errors.py, __init__.py}`

**`surfaces.py`:** `Surface(Flag)` = `API|MCP|CLI|NOTIFY` (NOTIFY REQUIRED). `Mode(StrEnum)` = exactly four: `REQUEST_RESPONSE, STREAMING, ASYNC_JOB` (→ job_id + status_poll), `WEBHOOK_INBOUND`.

**`decorator.py`:** `CapabilitySpec[I,O]` (frozen dataclass: name, input_model, output_model, handler, description, examples, surfaces, mode). `capability(...)` rejects empty description and `Surface(0)`; webhook_inbound cannot declare CLI.

**`registry.py`:** `Registry.register` (dup-name → `DuplicateCapabilityError`, HARD), `all()`, `for_surface(surface)`.

**`discovery.py`:** `discover_and_register(registry, modules)` — every logic package MUST expose `register(registry)`; a module missing it → `MissingRegisterError` (push registration, so capabilities never becomes a god-module).

**`errors.py`:** `CapabilityError` base; `CapabilityDeclarationError`, `DuplicateCapabilityError`, `MissingRegisterError`.

**TDD-first tests:** T-CAP-1 (Surface includes NOTIFY; set exactly {API,MCP,CLI,NOTIFY}); T-CAP-2 (Mode four values); T-CAP-3 (empty surfaces rejected); T-CAP-4 (empty description rejected); T-CAP-5 (webhook cannot be CLI); T-REG-1 (dup-name hard error); T-REG-2 (for_surface filters); T-DISC-1 (missing register raises); T-DISC-2 (push registration calls each once); T-CAP-6 (`test_capabilities_imports_only_stdlib_pydantic_typing` — AST scan, no atm_* logic, no fastapi/typer/mcp).

**Definition of Done:** all the above invariants pass; import set ⊆ {stdlib, pydantic, typing}; pyright/ruff clean.

---

#### [F0-CONFORMANCE-SKELETON] — full conformance harness, written RED
**package:** tests/conformance · **group:** G0 · **depends-on:** F0-CORE-INIT, F0-CAPS

Split into `static/` (AST/import-scan rules, no runtime) and `behavioral/` (runtime sentinel-driven) exactly per the §3 rule list. Each rule authored RED with BOTH a negative fixture AND the foundation-passing assertion. The honesty/tenant/tiktoken/rollup/provenance/signal-class/dependency-direction/no-type-outside-core rules go **green immediately**; the rest stay red (skip-marked with owning task ID, never silently xfailed).

**Behavioral formulations:** `no_secret_logging` — runtime sentinel: inject a known ingest/provider key, exercise capture/eval paths, assert it appears in no span attribute, no log record, no DB row (NOT a static grep). `sdk_fails_open` — inject a throwing client; host call still returns, exception logged not propagated. `honesty_axes_invariants` — construct illegal states (estimate-as-billed, inferred-as-exact, attempt-as-confirmed); each raises.

**Meta-tests:** `test_each_rule_flags_its_negative_fixture` (parametrized over all rule modules); `test_foundation_passing_rules_green`; `test_static_behavioral_split` (static needs no DB/network; behavioral marked needing runtime fixture); `test_no_secret_logging_is_runtime_sentinel`.

**Definition of Done:** each rule file (a) flags its synthetic negative fixture AND (b) passes against the foundation; foundation rules green now; remainder red-but-meaningful (skip-marked with owning task ID).

---

### GROUP 1 — CORE-EXTENSIONS (serial barrier)

G1 adds every remaining domain type the logic packages need into `core`, so no G2 package redefines a core type. Serial (shared `__init__`). C3 Protocols/ABCs (`OutcomesPredicateValidator`, `SignalClassMapper`, repository ABCs, `ReviewQueue`) fully declared here; real impls land G2, verified G5. **After G1, the core surface is FROZEN.**

#### [G1-CORE-CONTEXT] — context propagation + injected Protocols (H10)
**File:** `packages/core/src/atm_core/context.py`
```python
active_run_id: ContextVar[RunId | None] = ContextVar("atm_active_run_id", default=None)
@runtime_checkable class Clock(Protocol):    def now(self)->datetime: ...
@runtime_checkable class UuidGen(Protocol):  def new(self)->str: ...
@runtime_checkable class Rng(Protocol):      def random(self)->float: ...; def sample(self,population,k): ...
@runtime_checkable class Embedder(Protocol): def embed(self,texts)->Sequence[Sequence[float]]: ...
@runtime_checkable class ProviderClient(Protocol):
    def count_tokens(self,*,model,text)->int: ...; def complete(self,*,model,prompt)->str: ...
@runtime_checkable class LlmJudge(Protocol): def grade(self,*,prediction,reference,rubric)->float: ...
def run_in_context(fn,/,*args,**kwargs):     # copy_context().run — carries contextvars across ThreadPoolExecutor
    ctx = copy_context(); return lambda: ctx.run(fn,*args,**kwargs)
```
**Owners encoded (H10):** ThreadPoolExecutor copy_context + fork-degrade + baggage. `run_in_context` provided here; SDK (G3) patches `ThreadPoolExecutor.submit` to use it; fork-degrade rule (child has no ambient run_id → binding tier downgraded + labeled, never guessed) documented on `active_run_id`, tested at G2-ATTRIBUTION/G3.

**TDD:** `test_active_run_id_default_none`; `test_run_in_context_carries_run_id_across_thread` (raw submit does NOT); `test_protocols_runtime_checkable`.

#### [G1-CORE-EVAL] — eval models + repos (no plaintext key; no auto-switch)
**Files:** `packages/core/src/atm_core/eval/{models.py,repositories.py,__init__.py}`. `ProviderKeyRef` (`provider`, `secret_ref` = env var name/ARN — NO plaintext field, no `key`/`api_key`/`secret_value`). `CostGatePhase` (SMOKE, CONFIRMATION). `CostEstimate`, `EvalDataset`, `EvalCase`, `ModelCandidate`. `EvalRecommendation` with `grade: EvalGrade` (capped at directional off non-outcome/non-human label), parity_ci95, latency p50/p95/p99, sample_disagreements, gap_distribution, pareto_frontier, methodology, and **`auto_switch: Literal[False]`** (True unrepresentable). Repos `EvalDatasetRepository`, `EvalRecommendationRepository` (tenant_id first). **`grade_cap_invariant`** model_validator: `RELIABLE` only constructible with `label_source ∈ {OUTCOME_LABEL, HUMAN_LABELED}`.

**TDD:** `test_auto_switch_is_false_literal`; `test_provider_key_ref_has_no_plaintext_field`; `test_reliable_requires_outcome_or_human_label`; `test_recommended_none_when_no_separation`.

#### [G1-CORE-RECON-ALLOC] — recon/alloc extensions + repo methods (H7 carried)
**Files:** `packages/core/src/atm_core/models/{reconciliation.py,allocation.py}` extensions. `ProvenanceBreakdown` (§5.3a: reconciled/provisional/estimate_only usd + `pct_reconciled`). `AllocatedRollup` (lines, `pct_unallocated` honesty anchor §5.4, `confidence: RollupConfidence` — both H7 fields, `provenance_breakdown`). `DriftAlert` (match_key, drift_pct, ranked_causes). `AllocationRepository.get_rollup`; `ReconciliationRepository.list_drift_alerts`.

**TDD:** `test_allocated_rollup_carries_h7_fields`; `test_pct_unallocated_present`; `test_provenance_breakdown_sums`; `test_drift_alert_ranks_causes`.

#### [G1-CORE-CAPTURE-FIELDS] — pricing + run cost rollup
**Files:** `packages/core/src/atm_core/pricing.py` + extend `cost.py`/`rollup.py`. `PriceCard` (`provider, model, usd_per_mtok: Mapping[TokenClass,Decimal], effective_from, rule_version`). `PriceBook` (`cards`, `card_for(*,provider,model,at)`). Confirms per-provider per-class lookup; OpenAI has no cache-write price while Anthropic does (5m/1h distinct).

**TDD:** `test_price_card_per_token_class`; `test_openai_no_cache_write_price_modeled`; `test_pricebook_picks_effective_card_by_date`.

#### [G1-CORE-OUTCOMES-ATTR] — webhook result, binding fields, review queue ABC
**Files:** `packages/core/src/atm_core/webhook.py` + extend `attribution.py`; `repositories.py` gains `ReviewQueue` ABC + C3 Protocols. `WebhookResult` (`verified` — signature+ingest-key verified BEFORE parse, source, event_type, run_id|None, `extracted_via: Literal["echo","entity_fallback"]|None`, payload). `OutcomesPredicateValidator` (Protocol: `validate(expr)` AST-allowlist; raises on eval/exec/dunder). `SignalClassMapper` (Protocol: `map_signal(*,match_kind,declared)`; function/http can never yield outcome_confirmed unless authoritative). `ReviewQueue` (ABC: enqueue/list_pending, tenant_id first).

**TDD:** `test_webhook_result_verified_flag`; `test_signal_mapper_protocol_runtime_checkable`; `test_review_queue_methods_tenant_first`; `test_outcomes_predicate_validator_protocol_present`.

#### G1 EXIT — FREEZE CRITERIA (the barrier; H7) — NO G2 task starts until ALL hold:
1. Every core model is `frozen=True, extra="forbid", strict=True` (meta-test; missing flag is a blocker, never patched downstream).
2. Every domain event subclasses `TenantScopedModel` (`CostEvent, OutcomeEvent, Run, AttributionResult, ReconciliationRecord, AllocatedRollup, RunCostRollup, EvalDataset, EvalRecommendation` all carry required `tenant_id`).
3. Every repository ABC method has `tenant_id: TenantId` first (re-run T-REPO-1 over the complete set incl. eval repos + `ReviewQueue`).
4. The three honesty axes are the only system axes (`EvalGrade`/`ReconciliationState` not referenced by any field on core event models).
5. H7 both-fields rule — every rollup-shaped model carries a `RollupConfidence` with both `minimum_tier` + `confidence_distribution`.
6. `auto_switch` is `Literal[False]`; `ProviderKeyRef` has no plaintext field; `grade_cap_invariant` holds.
7. Config-AST model allowlist fixed now (the config-shaped pydantic models logic packages legitimately define for `outcomes.yaml`/`shared_costs.yaml` parsing) so G2 config models don't trip `no_type_outside_core`. Any new model outside the allowlist and outside core is a blocker.
8. Full core suite green; pyright strict clean; ruff clean; ≥90% line+branch on all `atm_core` submodules; `__all__` complete + explicit.

**G1 EXIT meta-tests:** `test_all_core_models_frozen_forbid_strict`; `test_all_domain_events_tenant_scoped`; `test_all_repo_methods_tenant_first_full_set`; `test_eval_grade_and_recon_state_not_event_fields`; `test_every_rollup_model_carries_both_h7_fields`; `test_config_model_allowlist_fixed`; `test_core_coverage_ge_90`.

---

### 