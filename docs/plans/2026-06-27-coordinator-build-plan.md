I have all the group details inlined in the prompt. This is a pure synthesis/assembly task — I need to produce the complete coordinator build plan document by assembling the per-group task details into the specified structure. Let me write it out directly as my final response.

# AI Margin Intelligence — Coordinator Build Plan (FINAL)

**Repo root:** `/Users/monaal/antitokenmaxxing/` (greenfield; only `docs/` + `.claude/` exist — every path below is to-be-created). **Toolchain:** `uv` workspace, Python 3.11+, pydantic v2, hypothesis, pytest, pyright `--strict`, ruff, import-linter, SQLAlchemy 2.x async + alembic, `testcontainers[postgres]>=4,<5`; TS SDK on `tsc --strict` + eslint + tsup (dual ESM/CJS). **Canonical prefix locked: `atm_`.** `ai_margin_*` / `atmx_*` are forbidden — fail any module declaring them.

---

## 1. BUILD DAG (with intra-group ordering)

```
G0 ─ FOUNDATION (serial, single worktree — shared atm_core/__init__.py)
   F0-TOOLING ─▶ { F0-CORE-1a, F0-CAPS }
   F0-CORE-1a ─▶ { F0-CORE-1b, F0-CORE-1c } ─▶ F0-CORE-INIT
   { F0-CORE-INIT, F0-CAPS } ─▶ F0-CONFORMANCE-SKELETON   (written RED)
        │
        ▼  (conformance-red: foundation rules green now, rest red-but-meaningful)
G1 ─ CORE-EXTENSIONS (serial barrier, single worktree)
   G1-CORE-CONTEXT ∥ G1-CORE-EVAL ∥ G1-CORE-RECON-ALLOC ∥
   G1-CORE-CAPTURE-FIELDS ∥ G1-CORE-OUTCOMES-ATTR
        │
        ▼  ╔═══════════ G1 EXIT — HARD FREEZE BARRIER ═══════════╗
           ║ core surface frozen; 7 EXIT meta-tests green;       ║
           ║ NO G2 task starts until all hold                    ║
           ╚═════════════════════════════════════════════════════╝
G2 ─ LOGIC FAN-OUT (parallel; ABC-isolated worktrees; code vs core ABCs/Protocols only)
   ┌─ G2-STORE  ── STORE-1 (schema + ALL migrations + tables.py)
   │                    │  ◀── G2-STORE SUB-BARRIER (C2): publish DDL before any
   │                    │       store-touching G2 work; RECON/ALLOC/METRICS never
   │                    │       run alembic autogenerate
   │              { STORE-2 repos ∥ STORE-3 raw-JSONB ∥ STORE-4 idempotent-upsert }
   │
   ├─ G2-CAPTURE      PG0 fail-open ─▶ PG1 pricing+invariants ─▶ PG2 instance-wrapt patch
   │                  ─▶ PG3 streaming-terminal ─▶ PG4 otlp wire ─▶ PG5 gateway+register
   ├─ G2-OUTCOMES     OUT-A rules ─▶ OUT-B function-patch+emit ─▶ OUT-C run_id-injection
   │                  ─▶ OUT-D webhook ─▶ OUT-E retraction+register
   ├─ G2-ATTRIBUTION  ATTR-0 resolver+scoring ─▶ ATTR-1 {t1∥t2∥t3} ─▶ ATTR-2 t4
   │                  ─▶ ATTR-3 t5 ─▶ ATTR-4 cascade+register
   ├─ G2-RECON        (after STORE sub-barrier) proration ─▶ matcher ─▶ drift ─▶ csv
   │                  ─▶ service ─▶ query+register
   ├─ G2-ALLOC        config ─▶ tier1 ─▶ tier2 ─▶ tier3 ─▶ rollup ─▶ service+register
   ├─ G2-METRICS      grammar ─▶ compiler ─▶ propagation ─▶ executor+register
   ├─ G2-EVAL         foundation ─▶ {discover∥dataset∥grade} ─▶ {search∥costgate}
   │                  ─▶ report ─▶ cadence ─▶ service ─▶ register
   └─ G2-ONBOARDING   foundation ─▶ scan ─▶ {propose∥suggest} ─▶ {validate∥render}
                      ─▶ {diff∥dryrun∥github} ─▶ service ─▶ register
        │
        ▼
G3 ─ SDKs + PACKAGING (parallel; H9 intra-order)
   PYSDK ─▶ PYPI-PKG          TSSDK ─▶ NPM-PKG          OTLP-CONTRACT (∥; consumes frozen semconv)
        │
        ▼
G4 ─ APPS (parallel; thin registry projections)
   API ∥ MCP ∥ CLI ∥ NOTIFY ∥ AGENT-INTEGRABILITY
        │
        ▼  ╔══════════ G5 INTEGRATION BARRIER (serial) ══════════╗
G5 ─ INTEGRATION + E2E + CONFORMANCE
   G5-INTEGRATION (real Postgres) ─▶ G5-E2E-CROSS-LANG (real wire)
   ─▶ G5-CONFORMANCE-GREEN  ◀── DEFINITION-OF-DONE GATE
           ╚═════════════════════════════════════════════════════╝
```

**Worktree rules:** G0 and G1 each run in a **single serial worktree** (every task touches shared `atm_core/__init__.py`). G2 fans out into **ABC-isolated parallel worktrees** — each logic package codes against `atm_core` ABCs/Protocols only, never imports `atm_store` or a sibling logic package. The **G2-STORE migration sub-barrier (C2)** sequences inside G2: STORE owns every migration; RECON/ALLOC/METRICS consume repo ABCs and never autogenerate.

---

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

### GROUP 2 — LOGIC FAN-OUT (parallel; ABC-isolated worktrees)

> Every G2 package: depends only on G1 (frozen `atm_core` + `atm_capabilities`); isolated worktree; codes against `atm_core` ABCs/Protocols only; never imports `atm_store` or a sibling logic package; ends with `register(registry)` (M10). Money `Decimal` ROUND_HALF_EVEN; tenant_id structurally required; TDD red→green→refactor; ≥90% line+branch. Intra-package integration runs against named core ABC stubs (real Postgres is G5) EXCEPT where a task explicitly runs real Postgres via STORE post-sub-barrier.

#### [G2-STORE] — packages/store (`atm_store`) — the persistence layer AND the C2 migration sub-barrier

**§0 INTRA-G2 SUB-BARRIER (C2) — FIRST, before any store-touching G2 work.** STORE authors **every** table schema and **every** alembic migration in the system. No other G2 task writes a migration or runs `alembic revision --autogenerate`. Order: **STORE-1 (schema/migrations) → barrier → {STORE-2 repos ∥ STORE-3 raw-JSONB ∥ STORE-4 idempotent-upsert}.** Publish the migration set + `tables.py` metadata before implementing repos.

**File tree:**
```
packages/store/
├── pyproject.toml         # deps: atm-core, sqlalchemy[asyncio]>=2,<3, asyncpg, alembic; dev: testcontainers[postgres]>=4,<5, pytest-asyncio
├── py.typed, alembic.ini
├── src/atm_store/
│   ├── __init__.py, engine.py, tables.py, types_pg.py, mappers.py, tenant_guard.py, capabilities.py
│   ├── repositories/{run,cost_event,outcome_event,attribution,reconciliation,allocation,raw_record}.py
│   └── migrations/{env.py, script.py.mako, versions/0001_initial_schema.py}
└── tests/{conftest.py, unit/, integration/, conformance/static/}
```

**STORE-1 (sub-barrier artifact):** `tables.py` = `MetaData()` + 8 `Table`s mirroring core models. Money columns `NUMERIC(20,10)` (never `Float`); timestamps `TIMESTAMP(timezone=True)`; JSONB for `atm_outcome_event.raw`/`entity_keys` and `atm_raw_record.raw`. Constraints: `atm_cost_event UniqueConstraint(tenant_id,run_id,attempt_id)` (drives idempotent upsert); `atm_outcome_event UniqueConstraint(tenant_id,correlation_id)`; `atm_reconciliation_record` PK-only, **no unique constraint** (append-only), index `(tenant_id,cost_event_id)`; every table has `tenant_id UUID NOT NULL` + leading index; match-key index `atm_cost_event(provider,model,captured_at)`. `0001_initial_schema.py` creates all 8 tables+indexes; `env.py` sets `target_metadata = atm_store.tables.metadata`.

**STORE-2 (repos):** each `Pg*Repository(sessionmaker)`; reads build `select(...)` through `tenant_guard.require_tenant(stmt, tenant_id, table)` (so AST conformance can prove no query omits tenant scope). `PgCostEventRepository.upsert` uses `on_conflict_do_update(index_elements=[tenant_id,run_id,attempt_id])`; `PgOutcomeEventRepository.upsert` conflict on `(tenant_id,correlation_id)`; `.retract` does `select...for update`, raises `ValueError` if not confirmed, else flips to retracted.

**STORE-3 (raw JSONB):** `PgRawRecordRepository.put/get` byte/structure-identical round-trip (H2: real Postgres, no SQLite parity).

**STORE-4 (idempotent upsert):** covered by conflict clauses; tested explicitly.

**`capabilities.py`:** `register(registry) -> None: return None` — STORE is an adapter, exposes no product capability; hook exists so `discover_and_register` calls it uniformly (M10).

**TDD specs (RED first):** `test_require_tenant_appends_where_clause`; `test_every_repository_method_routes_through_require_tenant` (AST, negative fixture flagged); `test_reconciliation_repo_has_no_update_or_delete` (AST); `test_money_column_is_numeric_not_float` + `test_decimal_roundtrips_without_float_drift`; `test_double_upsert_same_key_yields_one_row` (real PG); `test_retract_confirmed_flips_to_retracted` + `test_retract_non_confirmed_raises`; `test_two_appends_same_event_yield_two_rows` (append-only); `test_nested_jsonb_roundtrips_identically`; `test_tenant_a_cannot_read_tenant_b_rows`; `test_idle_quarantine_flag_persists`; `test_every_model_roundtrips_through_row`; `test_migration_no_autogen_drift` (apply 0001, run autogenerate, assert empty upgrade body). `conftest.py`: session-scoped `PostgresContainer("postgres:16")`, `alembic upgrade head` once, per-test transaction rollback.

**Conformance turned green:** `tenant_scoping`, `additive_reconciliation`, `migration_no_autogen_drift`.

**Definition of Done:** all 8 tables + migrations published before any store-touching G2 task; all 7 repos implemented tenant-scoped; money is NUMERIC(20,10), no float; recon append-only; JSONB byte-fidelity on real PG; idempotent upserts never double-count; autogenerate yields empty diff; ≥90% coverage; pyright/ruff clean.

---

#### [G2-CAPTURE] — packages/capture (`atm_capture`)
Consumes `CostEvent`, `TokenVector`, `ProvenanceLabel`, `PriceBook`, `active_run_id`, `Clock`, `UuidGen`, `CostEventRepository` ABC. **Intra-package sub-DAG (PG0→PG5).**

**File tree:** `src/atm_capture/{__init__.py, sources/{base,client_instrument,otlp_ingest,provider_costapi,gateway}.py, pricing/compute.py, streaming/{accumulator,terminal}.py, invariants.py, emit.py, guard.py, otlp/semconv.py, selftest.py, capabilities.py}` + `tests/{unit,integration,wire_contract/semconv_keys.json}`. deps add `wrapt>=1.16, httpx>=0.27`.

**PG0 fail-open (sub-barrier first):** `guard.py` — `guard(logger,*,drop_counter)` swallows ONLY our telemetry exceptions, never the host's; the host call is OUTSIDE the guard (`result = wrapped(*args,**kwargs)` then `with guard(): _capture_from(result)`). `emit.py` — `Emitter` bounded queue (`max_queue=10_000`), non-blocking, drop-and-count, never raises. **TDD:** guard suppresses ours / doesn't catch host's; emit drops+counts when full; emit never raises on repo failure; off-path overhead (enqueue not synchronous write). Green: `sdk_fails_open`.

**PG1 pricing+invariants:** `compute_cost_usd(tokens, card)` sums per-class `(tokens/1e6)*usd_per_mtok`, Decimal, quantize `0.000001` ROUND_HALF_EVEN; OpenAI cache_write priced 0. `check_invariants(...)` returns the six provenance_warnings (never raises, never silent — the lenient OTLP-coerced path). **TDD:** decimal half-even; never float (monkeypatch float to raise); OpenAI cache_write zero + warning; cache>total_input warns; reasoning>output warns; hypothesis proration property. Green: `no_tiktoken_for_cost`.

**PG2 the H1 instance-scoped wrapt patch + self-test:** `instrument_client(client,...)` wraps the injected client's own transport (`client._client.send` via `wrapt.wrap_function_wrapper` on the INSTANCE), NEVER `httpx.Client.send` at module/class level. `_send_wrapper` stamps `attempt_id`, reads `active_run_id`, emits per-attempt CostEvent (fail-open, host outside guard). Returns reversible `InstrumentHandle.uninstrument()`. `selftest.py` checks installed openai/anthropic/httpx versions vs `KNOWN_GOOD`; on out-of-range or absent hook → loud warning + downgrade granularity to `per_call` (tagged, never silent). **TDD (headline H1):** `test_unrelated_httpx_client_is_untouched`; per-attempt emit; retry → two events one per attempt; patch doesn't swallow host transport error; uninstrument restores; selftest warns+degrades on bad version / ineffective patch; run_id from active contextvar. Green: `granularity_labeled`.

**PG3 streaming terminal-value rules (the 2× fix):** `terminal.py` — Anthropic: OVERWRITE output from `message_delta.usage.output_tokens` (never sum); cache tokens from `message_start` ONCE (summing is the `@langchain/anthropic` 2× bug); 5m/1h from nested `cache_creation.ephemeral_5m/1h_input_tokens`; reasoning = thinking-block count. OpenAI: REQUIRE `stream_options.include_usage`; usage in final chunk only; absent → flag partial. `AnthropicStreamAccumulator`/`OpenAIStreamAccumulator`. **TDD:** delta output overwritten not summed; cache taken from message_start not doubled; 5m/1h split from nested; reasoning derived; openai requires include_usage; cancelled recovers partial else flags; hypothesis "terminal for any delta sequence". Green: `streaming_no_delta_sum`.

**PG4 OTLP wire contract (single source of truth):** `otlp/semconv.py` — every literal key a module constant: standard `gen_ai.*` + `ai_margin.*` extensions (cache_read, cache_write_5m/1h, reasoning, run_id, attempt_id, tenant_id, provenance, capture_granularity, cost_usd, is_streaming, partial_recovered); `ALL_KEYS`; `generate_semconv_fixture(path)` writes `{"keys": sorted(ALL_KEYS)}`. `otlp_ingest.py` — `span_to_cost_event(attrs,*,tenant_id,pricebook,clock)` maps via constants only; tenant_id MANDATORY param. **TDD:** fixture matches committed json; no duplicated string literals (AST asserts only semconv constants referenced); span→CostEvent round-trip; authoritative inline cost used when present; tenant required. Green: `wire_semconv_parity` (Py side).

**PG5 gateway + provider_costapi + register:** `gateway.py` OpenRouter — `usage.cost` authoritative inline → `provider_reconciled`, per_attempt; refuses vendor self-declared estimate. `provider_costapi.py` — marker source only (true-up lives in recon); PTU refusal (H10): provisioned-throughput → `cost_usd=None` + warning `billing_uncertain_abort: provisioned_throughput`. `capabilities.py::register` adds `ingest_otlp_span` (webhook_inbound, API), `list_cost_sources`, `capture_healthcheck` (request_response, API|MCP|CLI). **TDD:** OpenRouter provider_reconciled; refuses estimate; PTU refuses token-derived cost; register adds all three; ingest declares webhook_inbound; intra-package integration `test_ingest_span_persists_via_repo_stub` (idempotent on (run_id,attempt_id)).

**Conformance green:** `sdk_fails_open`, `no_tiktoken_for_cost`, `streaming_no_delta_sum`, `granularity_labeled`, `wire_semconv_parity` (Py). **Definition of Done:** all PG0–PG5 sub-barriers green; H1 instance-scope proven; fail-open proven; semconv fixture committed; ends with `register`; ≥90% coverage; pyright/ruff clean.

---

#### [G2-OUTCOMES] — packages/outcomes (`atm_outcomes`)
Consumes `SignalClass`, `BindingTier`, `OutcomeEvent`/`OutcomeBinding`, `WebhookResult`, `active_run_id`, `OutcomesPredicateValidator` + `SignalClassMapper` Protocols, `OutcomeEventRepository` ABC. **Sub-DAG OUT-A→E.** deps add `wrapt>=1.16, pyyaml>=6`.

**OUT-A rules schema+loader:** `MatchSpec` (exactly one of function/http/db_write/status_transition/webhook; `when` predicate string, never eval'd; `match_kind` property), `RunIdInjectionSpec` (sdk_call, inject_into, webhook_event, extract_from), `OutcomeRule` (name, match, value, bind, run_id_injection, signal — declared preference, mapper has final say). `loader.load_rules(text,*,validator)` uses `yaml.safe_load` (never `load`); validates each `when`/`value` via injected `OutcomesPredicateValidator`. **TDD:** safe_load not load (`!!python/object` raises); eval predicate rejected (spy asserts validator consulted); dunder blocked; exactly-one-match-kind; run_id_injection round-trips; valid rule compiles.

**OUT-B function-patch+emit:** `install_function_rules(...)` wrapt-wraps named symbols; AFTER host call, if compiled `when` is True over `{args,kwargs,result}` → build+emit OutcomeEvent (run_id from active_run_id; host outside guard). `OutcomeEmitter.emit(...)` — `signal_class = mapper.map_signal(match_kind=..., declared=rule.signal)` (system-owned; function/http never confirmed); idempotency `correlation_id or (source,external_id)`; non-blocking, fails open. **TDD:** function match cannot emit confirmed (system overrides declaration); webhook can; predicate gates emission; value/entity_keys via compiled (no eval); idempotent on double delivery; doesn't swallow host error; fails open on repo error.

**OUT-C T3 run_id injection:** `install_run_id_injection(...)` wraps each declared `sdk_call`; reads active run_id and **copy-on-write** merges into `inject_into` path (`_merge_path` deep-copies only the spine, never mutates caller's dict). Unresolved sdk_call at init → STARTUP WARNING naming it, recorded, never silent no-op. **TDD:** run_id merged into outbound kwargs; copy-on-write (caller's original unchanged); no run_id no injection; unresolved warns not silent; doesn't swallow host error.

**OUT-D webhook ingest:** `receive_webhook(...)` ORDER: (1) verify signed-secret per source (HMAC `compare_digest`) AND ingest key BEFORE parsing; never log secret/ingest-key; (2) parse after verification; (3) extract run_id via `extract_from` — present → `tier=deterministic, bound_by='t3_webhook_echo'`; absent → `tier=candidate, bound_by='t4_entity_pending'` + entity_keys (labeled, never silently mis-bound); (4) signal via mapper; (5) idempotency. **TDD:** unverified signature rejected before parse (secret never in logs); t3 echo binds deterministic; no echo falls to t4 candidate labeled; idempotent; constant-time compare.

**OUT-E retraction + register:** `retract_outcome(...)` flips confirmed→retracted only (status guard), idempotent. `register` adds `ingest_webhook_outcome` (webhook_inbound, API), `validate_outcome_rule`, `list_outcome_rules` (request_response, API|MCP|CLI). **TDD:** retract flips only confirmed; idempotent; register adds all three; validate capability rejects eval predicate; intra-package `test_webhook_persists_via_repo_stub` (tenant-scoped).

**Conformance green:** `no_eval_in_predicate`, `signal_class_never_user_set`, `no_secret_logging`. **Definition of Done:** OUT-A→E green; predicates safe; signal system-owned; secrets never logged; copy-on-write injection; ends with `register`; ≥90% coverage; pyright/ruff clean.

---

#### [G2-ATTRIBUTION] — packages/attribution (`atm_attribution`)
The binding cascade T1→T5. Consumes `BindingTier`, `AttributionResult`/`AttributionCandidate`, `ConfidenceLabel`, `active_run_id` + baggage accessor, `RunRepository`/`ReviewQueue` ABCs, `LlmJudge` Protocol. **Sub-DAG ATTR-0→4.**

**ATTR-0 resolver Protocol + system-owned scoring:** `Resolver` Protocol (one `tier` it may ever produce). `ResolveContext`/`ResolveOutcome` (candidates each `tier==resolver.tier`; `ambiguous` flag). Invariant `resolver_emits_only_its_own_tier` via `__init_subclass__`/runtime assert + conformance test. `confidence/scoring.py` — system-owned `_TIER_TO_LABEL` (exact/deterministic→high, candidate→medium, likely→advisory); `label_for(tier)`; NO setter. **TDD:** candidate tier must match resolver tier; map system-owned no setter; `no_user_override_of_confidence_mapping`.

**ATTR-1 deterministic resolvers (parallel):** `t1_ambient` (exact, only when context propagated; None → `matched=False`, never mis-bind), `t2_baggage` (exact, W3C baggage), `t3_roundtrip` (deterministic, echoed_run_id). **TDD:** t1 exact when ambient present / no-match when absent; t2 exact from baggage; t3 deterministic from echo / no-match without; each emits only its own tier.

**ATTR-2 t4 entity (candidate):** query `RunRepository.find_runs_for_entity` (±W window), tie-break by time proximity, ε-tie → `ambiguous=True` (halt to review), never promotes to deterministic. **TDD:** single match candidate; time-window tie-break (both returned, closer higher score); ε ambiguity halts; tenant-scoped (different tenant never returned); only candidate tier.

**ATTR-3 t5 semantic (likely; off without judge):** `judge is None` → DISABLED (`matched=False`); else `judge.judge(...)` → `tier=likely`, always review-queued, never billing-grade. **TDD:** disabled without judge; likely + always review; never billing-grade; only likely tier.

**ATTR-4 cascade + register:** `Cascade.bind(ctx)` walks T1..T5 ordered; T1/T2/T3 first match SHORT-CIRCUITS → billing-grade, `review_required=False`; **fast-path revalidation** confirms run still exists (run_repo) before accepting a deterministic run_id, else DOWNGRADE (never bind a ghost); T4 candidate → `review_required=True`, enqueue; T4 ambiguous → HALT, enqueue all; T5 likely → review, never billing; no match → unbound, review. candidate/likely ALWAYS `review_required=True`. `register` adds `bind_outcome`, `list_review_queue` (request_response, API|MCP|CLI). **TDD:** short-circuits on first deterministic; order t1 before t4; fast-path revalidates dangling run; t4 ambiguity halts+enqueues all; candidate/likely always review (not billing-grade); no-match unbound; confidence label matches tier; resolver-emits-own-tier across cascade; intra-package `test_bind_persists_review_via_queue_stub` (tenant-scoped).

**Conformance green:** `resolver_emits_only_its_own_tier`, `candidate_likely_never_billing_grade`, `no_user_override_of_confidence_mapping`. **Definition of Done:** cascade short-circuits + revalidates + halts on ambiguity; candidate/likely never billing-grade; confidence map system-owned; ends with `register`; ≥90% coverage; pyright/ruff clean.

---

#### [G2-RECON] — packages/reconciliation (`atm_reconciliation`)
Consumes `ReconciliationRecord`, `ProvenanceBreakdown`, `Provenance`, `ReconciliationRepository`/`CostEventRepository` ABCs. Uses STORE tables only through repo ABCs; never autogenerate, never writes a migration. deps add `hypothesis, pytest-asyncio`.

**Files:** `src/atm_reconciliation/{proration,matcher,drift,manual_csv,provider_api,service,query,capabilities}.py`.

**proration.py (money heart):** `prorate(estimates, billed_total)` — `proration_factor = billed_total/sum(estimates)`, scale each, quantize `0.0000000001` (10dp = NUMERIC(20,10)) ROUND_HALF_EVEN, then **largest-remainder** absorbs residue so `sum == billed_total` exactly. Pure, no float; raises if `sum(estimates)==0 and billed_total!=0`. **matcher.py:** `group_by_match_key` → `"{provider}|{project}|{model}|{token_class}|{day}"`. **drift.py:** `classify_drift` — `|drift|<10%` noise; `>10%` alert with `ranked_causes` from `[cache_mispricing, negotiated_rate, batch_discount, credits, tax]`. **manual_csv.py:** `parse_manual_csv` (Bedrock/Vertex/Azure) → `MANUAL_RECONCILED`; missing required column → typed error. **provider_api.py:** Protocol boundary; injected client, never logs the key. **service.py:** `reconcile_day(...)` lists window, groups, prorates, appends additive `ReconciliationRecord(delta=reconciled-estimate)` — NEVER mutates CostEvent estimate; re-run appends new records that supersede by `reconciled_at` (old retained for audit). **query.py:** `build_breakdown(...)` partitions reconciled/provisional/estimate_only; `by_provenance` sums to total; carries `drift_alerts` (M3, never silently swaps a number).

**TDD:** half-rounds-to-even; **hypothesis** prorated always sums to billed; no float in proration; record carries immutable estimate + delta (additive, original unchanged); service never calls cost_repo.update (AST); drift under/over 10% boundary + ranked cause; csv rows → manual_reconciled; (real PG via STORE) reconcile writes additive records summing to billed; reprocess trailing window supersedes (both sets persist, latest wins); mixed-state query breakdown sums + drift carried.

**Conformance green:** `additive_reconciliation`, `no_secret_logging` (provider key injected, never logged). **register:** `reconcile_day`, `cost_breakdown` (request_response, API|MCP|CLI). **Definition of Done:** prorations sum exactly (Decimal); additive never mutates; drift ranked; manual CSV labeled; mixed-state breakdown carried; ends with `register`; ≥90% coverage.

---

#### [G2-ALLOC] — packages/allocation (`atm_allocation`)
Consumes `AllocatedLine`, `AllocatedRollup`, `AllocationTier`/`Provenance`, `RollupConfidence`, `SharedCostsConfig`, `AllocationRepository` ABC. deps add `pyyaml, hypothesis, pytest-asyncio`.

**Files:** `src/atm_allocation/{config,tier1,tier2,tier3,rollup,service,capabilities}.py`.

**config.py:** `load_shared_costs(text,tenant_id)` via `yaml.safe_load`; absent → `SharedCostsConfig(inputs=())` (Tier-1-only mode). **tier1.py:** `direct_lines(events)` — one MEASURED line per event; `cost_usd is None` (PTU) excluded + counted into pct_unallocated rationale. **tier2.py:** `tier2_lines(shared, weights)` — proportional split using the SAME ROUND_HALF_EVEN largest-remainder allocator as reconciliation; every line ALLOCATED, carries allocation_key/rule_version/sensitivity_pct/confidence. **tier3.py:** `tier3_lines(shared)` — fixed overhead; `is_idle_gpu` → `is_quarantined_idle=True`, EXCLUDED from `fully_loaded_usd` (reported beside, never smeared — CloudZero 75%-util pattern). **rollup.py:** `build_rollup(lines, total_true_cost_estimate)` — fully_loaded = tier1+tier2+(tier3 non-idle); `quarantined_idle_usd`; `pct_unallocated` honesty anchor; `confidence_distribution` Counter of line.confidence; `minimum_confidence` least-trusted present, NEVER raised by aggregation. **service.py:** persists via `alloc_repo.upsert_line`, reads via `list_for_run`.

**TDD:** absent yaml → tier1-only with pct_unallocated surfaced; **hypothesis** proportional split sums exactly; tie breaks half-even; tier1 measured / tier2-3 allocated + carry key+version; AST any tier2/3 line with allocation_key None is a violation; idle GPU excluded from fully_loaded; pct_unallocated computed (e.g. 0.37 tokens-only); H7 minimum_confidence is least-trusted + distribution; (real PG) persist mixed tiers + rollup survives round-trip.

**Conformance green:** `rollup_carries_confidence`. **register:** `allocated_cost_rollup` (request_response, API|MCP|CLI). **Definition of Done:** three-tier split sums exactly; idle GPU quarantined beside; pct_unallocated surfaced; H7 fields present; ends with `register`; ≥90% coverage.

---

#### [G2-METRICS] — packages/metrics (`atm_metrics`)
The typed mini-DSL (closed allowlist, no free-text SQL/eval), compiler, H7/H8-correct propagation. Consumes `MetricDefinition`/`MetricCell`/`MetricResult` core models + read repo ABCs (tested against in-memory stub; real Postgres wiring is G5, H6). deps add `hypothesis, pytest-asyncio`.

**Files:** `src/atm_metrics/{grammar,compiler,propagation,executor,capabilities}.py`.

**grammar.py:** `validate_definition(d)` enforces closed allowlist (every filter field/values, group_by Dimension, aggregation, numerator/denominator combos; `cost_per_outcome` REQUIRES `denominator="verified_outcome_count"`); no free-text SQL, no eval/exec; raises `MetricGrammarError`. **compiler.py:** `compile(d) -> QueryPlan` PURE (no DB/IO/SQL string; same input → identical plan). **propagation.py:** `propagate(tiers)` → (minimum_tier = least-trusted present, Counter); `is_billing_grade` (exact/deterministic only); `denominator_outcomes(outcomes)` — include only `OUTCOME_CONFIRMED` AND tier in (exact,deterministic); candidate/likely EXCLUDED from denominator but COUNTED in distribution; `OUTCOME_RETRACTED` EXCLUDED + counted in `retracted_excluded_count`, metric re-emitted annotated (H8). **executor.py:** runs the plan against injected repo ABCs → `MetricResult` with all H7/H8 fields.

**TDD:** grammar rejects free-text/raw-SQL (AST asserts no eval/exec); rejects unknown dimension; compiler deterministic+side-effect-free (no IO deps); minimum_tier is min; candidate not in denominator but counted (2 exact + 3 candidate → denom 2, dist counts 5); retracted removed + `retracted_excluded_count==1` + re-emitted; **hypothesis** aggregate minimum never exceeds any member; executor end-to-end on in-memory stub.

**Conformance green:** `rollup_carries_confidence` (MetricCell carries both H7 fields), `no_eval_in_predicate` (DSL/compiler no eval/exec/free-text SQL). **register:** `run_metric` (request_response, API|MCP|CLI). **Definition of Done:** DSL closed-allowlist + no eval; compiler pure; H7/H8 propagation correct; ends with `register`; ≥90% coverage.

---

#### [G2-EVAL] — packages/eval (`atm_eval`)
Eval-backed model recommendation (evidence layer). Consumes `atm_core.eval` models, context Protocols (`Clock,UuidGen,Rng,ProviderClient,LlmJudge,Embedder,OutcomesPredicateValidator`), `EvalRunRepository`/read repo ABCs. Never imports a concrete store/surface framework/tiktoken/sibling logic package. deps add `scipy, numpy, hypothesis, pytest-asyncio`. **Sub-DAG:** FOUNDATION → {discover∥dataset∥grade} → {search∥costgate} → report → cadence → service → register → integration → e2e.

**FOUNDATION:** `errors.py` (`EvalError`, `BudgetExceededError`, `GateNotApprovedError`, `GroundTruthUnavailableError`, `JudgeNotValidatedError`). `stats.py` pure: `wilson_ci`, `percentiles(p50/p95/p99)`, `ci_separated`, `relative_improvement`, `meets_hysteresis(>=0.15)`, `underperforms_by(<25%)`. **TDD:** wilson edge/known values; percentiles monotone/empty raises; ci_separated; underperforms 25% boundary (strict <); hysteresis 15%; relative_improvement(0,0)==0.

**DISCOVER (`drain.py`/`discover.py`):** `templatize`/`skeleton_hash` (hash skeleton not filled string); `tool_set_fingerprint` (order-independent); `discover_clusters` — group_by backbone first, Drain for residue, embedding only if embedder present (else residue stays in a drain bucket, never dropped); every cluster `confirmed=False`. **TDD:** skeleton hash ignores literals; deterministic; fingerprint order-independent; group_by clusters by identity; drain when no identity; embedding skipped when embedder None (no run dropped); every cluster unconfirmed; task_type detected structurally.

**DATASET (`dataset.py`):** `build_dataset` stratified (frequent/long_tail/adversarial/failure; **oversample outcome-bound** — all included before sampling remainder via rng); version increments; source_trace_id back-links; reference_output = incumbent output. `validate_judge` — TPR/TNR vs human_label; `validated = tpr>=0.9 and tnr>=0.9 and n>=50`; ship committed `human_labels_n50.json`. **TDD:** four strata present; outcome-bound oversampled (all 10 included); version increments; every case has source_trace_id; reference is incumbent; below-n50 not validated; tpr<0.9 not validated; passes at n50/0.92; deterministic with seeded rng.

**GRADE (`grade.py`):** `select_label_source(...)` — outcome_label only if `predicate_validator.is_outcome_reconstructible_from_output(task_type)` AND labels present; else human → validated_judge → reference. `grade_for_label_source` — outcome/human → reliable; judge/reference → directional (grade_cap). `grade_case(...)`. **TDD:** outcome_label chosen when reconstructible; **rejected for open_ended even with labels** (the honesty test); falls human→judge→reference; grade caps (outcome/human reliable; judge/reference directional); reference uses judge; validated_judge with judge None raises.

**SEARCH (`search.py`):** `smoke_eval` (n∈[30,50], survivors = NOT `underperforms_by(>25%)`, NO CI; cap top-3); `confirmation_eval` (200..500); `pick_winner` — wins iff parity >= incumbent AND `ci_separated` (95% CI); None if nothing separates; OSS costed fully-loaded. **TDD:** smoke eliminates below 25% no CI; keeps within 25%; caps survivors to 3; confirmation requires CI separation; winner when CI separates; lowest-cost among separated; recommended None when nothing separates; OSS fully-loaded.

**COSTGATE (`costgate.py`):** `estimate_smoke_cost` — exact input via `provider.count_input_tokens` (NEVER tiktoken), output via sample-first 5%-extrapolate, Decimal ROUND_HALF_EVEN. `make_phase1_approval` (refuses if over budget; auto-approve under ceiling). `estimate_full_run_cost`/`make_phase2_approval` — phase-2 cannot be constructed before phase-1 approved (`two_phase_gate_ordered`). `resolve_provider_key(ref)` — local string from env/secret-manager; never on any model, never logged, never returned. **TDD:** provider tokenizer not tiktoken (AST); output sampled at 5% extrapolated; money half-even; phase1 refuses over budget; auto-approves/manual; phase2 requires phase1 approved; phase2 uses measured smoke output; key never on any model; **key never logged (runtime sentinel `SENTINEL_KEY_8f3a`)**.

**REPORT (`report.py`):** `build_recommendation(...)` carries parity+95% CI, cost_delta + projected $/month at real volume, latency p50/p95/p99, sample disagreements, gap_distribution across cohorts, pareto with dominated flag, methodology, `auto_switch=False`. `render_markdown` derives FROM the JSON (JSON source of truth). **TDD:** parity with CI; latency p50/95/99 monotone; disagreements; gap_distribution per cohort; pareto dominated flag; auto_switch False (True raises); grade reflects label source; JSON source of truth / markdown derives; methodology records label_source+human_count; recommended None renders "no switch".

**CADENCE (`cadence.py`):** `should_reeval(trigger)` — only the four CadenceTriggers, NO timer/interval param. `surface_switch_if_warranted` — block if not `meets_hysteresis(0.15)` vs prior. **TDD:** accepts only known triggers; no timer API (AST); hysteresis blocks sub-15%; allows 15%; first always surfaces.

**SERVICE + REGISTER:** `EvalService` (all deps injected, no global state, no concrete store). `register` adds `discover_agents` (request_response), `run_eval_funnel` (**async_job**), `get_recommendation` (request_response, includes NOTIFY), `approve_gate` (request_response). **TDD:** register adds all four; funnel is async_job; get_recommendation includes notify; each has description+examples; `test_eval_imports_no_surface_or_store` (AST — no fastapi/typer/mcp/atm_store/tiktoken). Integration vs in-memory repo ABC stubs (tenant-scoped, no leak, phase-gate order, budget-exceeded → no persist). E2E full funnel over fakes (complete Recommendation; sentinel key never persisted/logged/returned).

**Conformance green:** `grade_cap_invariant`, `no_auto_switch`, `two_phase_gate_ordered`, `smoke_no_ci_confirm_requires_ci`, `no_tiktoken_for_cost`, `no_secret_logging` (runtime sentinel), `no_logic_to_surface_import`, `no_type_outside_core`. **Definition of Done:** full funnel green over fakes + repo-ABC stub; grade caps + CI gates + auto_switch=False enforced; no tiktoken; sentinel key never leaks; ends with `register`; ≥90% coverage.

---

#### [G2-ONBOARDING] — packages/onboarding (`atm_onboarding`)
The onboarding agent: scan→propose→validate→exec→reviewable-diff. Consumes `atm_core.onboarding` models, `SignalClassMapper`/`OutcomesPredicateValidator` Protocols, `MetricsRollupReader` ABC (C3 — real metrics/store injected at G4/G5). Never imports concrete store/surface/sibling logic package. deps add `libcst, pyyaml`. **Sub-DAG:** foundation → scan → {propose∥suggest} → {validate∥render} → {diff∥dryrun∥github} → service → register.

**FOUNDATION:** `errors.py` (`OnboardingError`, `SecretEncounteredError`, `UnsafePredicateError`, `GithubScopeError`). `redact.py` — `SECRET_PATTERNS` (sk-ant, sk-ant-admin01, OpenAI sk-, AWS AKIA, assignment-form, high-entropy, Bearer); `contains_secret`, `redact` (idempotent), `assert_no_secret`. Used on EVERY string before it reaches a proposal field/diff/log. **TDD:** detects anthropic/admin/openai/aws keys + assignment form; redact replaces+idempotent; assert_no_secret raises; clean text unchanged.

**SCAN (`scan.py`):** AST (libcst) finds run boundaries, outcome sites (status setters, ORM writes, outbound Stripe/CRM/email, webhook handlers), durable entity IDs; every captured string `redact()`-ed; `detect_echoes_metadata` via `ECHOING_SYSTEMS` allowlist (Stripe/HubSpot/Zendesk → True; Salesforce → False). **TDD:** finds status setter / webhook handler / external write (echoes True); Salesforce no-echo; captures entity ids; finds run boundaries; never emits planted secret (deep dump); read-only (mtimes unchanged).

**PROPOSE (`propose.py`):** `build_proposal(...)` — `signal = signal_mapper.map_signal(...)` (system-owned); in-process → exact; echoing external-write → T3 `RunIdInjection`, deterministic; non-echoing external-write → no injection, candidate + warning naming the system + T4 fallback; `shared_costs_present=False` unless Tier-2/3 inputs (M6). **TDD:** echoing → t3 deterministic; non-echoing → t4 candidate with warning; function site cannot become confirmed; status_transition exact; shared_costs absent when no inputs; proposal contains no secret.

**SUGGEST (`suggest.py`, H10):** `suggest_attribution_rule(nl, source, ...)` → `SuggestedRule` with `confirmed=False` (drafts, never guesses-and-applies); confidence from match directness; nl+source redacted first. **TDD:** returns unconfirmed; maps nl to concrete site; signal system-mapped; low confidence when no matching site; redacts secret in source.

**VALIDATE (`validate.py`):** `validate_rule(...)` — `when` via `predicate_validator.validate` (raise `UnsafePredicateError`); re-assert signal == mapper output. **TDD:** rejects eval/dunder; accepts safe comparison; rejects user-set confirmed on function site.

**RENDER (`render.py`):** deterministic `render_outcomes_yaml` (stable-sorted, no timestamps; round-trips via safe_load), `render_shared_costs_yaml` (None when no inputs, M6), `render_agents_md_snippet`. **TDD:** deterministic; round-trips; matches committed expected fixture; t3 injection block present; shared_costs None when no inputs; no secret.

**DIFF (`diff.py`, H12):** `build_reviewable_diff(...)` — hunks only, never whole files; every hunk `assert_no_secret` (redact or drop+warn). **TDD:** only hunks not whole files; inserts init at run boundary; adds outcomes.yaml; never contains secret; excludes unmodified files.

**DRYRUN (`dryrun.py`, C3):** `dry_run(...)` via injected `MetricsRollupReader.cost_per_outcome` → `DryRunPreview` carrying both H7 fields. **TDD:** returns preview; carries minimum_tier+distribution; uses injected ABC not concrete (AST — no atm_metrics/atm_store import); no outcomes → None cost.

**GITHUB-APP (`github_app.py`, H12):** `ReadOnlyGithubApp` exposes ONLY `read_file` (in-process, never off-box) + `open_pr`; NO push/write_file/transmit_contents method exists. `assert_scopes` rejects scopes beyond `{contents:read, pull_requests:write}`. `open_pr` runs `assert_no_secret` before opening. **TDD:** no push/write_file/transmit method; assert_scopes rejects excess / accepts exact; open_pr rejects diff with secret; only writes PR-branch diff.

**SERVICE + REGISTER:** `OnboardingService` (injected mapper/validator/rollup_reader/optional github_app). `register` adds `scan_codebase`, `suggest_attribution_rule`, `validate_outcome_rule`, `dry_run_outcomes` (**async_job**), `propose_onboarding_diff` (rest request_response, API|MCP|CLI). **TDD:** register adds all five; suggest present (H10); dry_run async_job; `test_onboarding_imports_no_surface_or_concrete_store` (AST). Integration vs in-memory rollup ABC stub (reviewable diff, deterministic yaml, H7 previews, no secret anywhere, non-echoing site flagged t4). E2E scan→diff→(mock) read-only PR (body carries only diff, no exfil method, planted secret never appears).

**Conformance green:** `no_raw_source_exfil`, `no_secret_logging` (runtime sentinel), `no_eval_in_predicate`, `signal_class_never_user_set`, `no_logic_to_surface_import`, `no_type_outside_core`, `rollup_carries_confidence` (dry-run preview). **Definition of Done:** scan read-only + secret-safe; proposals system-mapped + T3/T4 labeled; diff hunks-only no secrets; github app has no exfil path; suggest returns unconfirmed; ends with `register`; ≥90% coverage.

---

### GROUP 3 — SDKs + PACKAGING (parallel; H9 intra-order)

> H9: PYSDK before PYPI-PKG; TSSDK before NPM-PKG; OTLP-CONTRACT parallel (consumes frozen semconv + TSSDK's semconv.ts). Packaging tasks excluded from coverage gate; their tests must pass.

#### [G3-PYSDK] — Python SDK (`sdks/python`, `atm-margin` / `atm_margin`)
**Depends on:** G2-CAPTURE, G2-OUTCOMES, G1 core. **Blocks:** G3-PYPI-PKG. A thin façade; all real instrumentation lives in the G2 packages it calls.

**File tree:** `src/atm_margin/{__init__.py, py.typed, _version.py, config.py, init.py, track.py, scaffold.py, errors.py}` + `tests/{conftest.py, e2e/}`.

**`InitConfig`** (frozen/forbid/strict): `tenant_id: TenantId`, `ingest_key: SecretStr` (never in repr/log/dump), `endpoint: str` (validator rejects non-http(s)), `capture_content: bool=False` (off by default §9.1), `outcomes_yaml_path/shared_costs_yaml_path: Path|None=None`, `service_name: str`, `max_queue_size: int=10_000`, `fail_open: Literal[True]=True` (SDK can never be configured to crash host).

**`init()`** returns `InitResult` (`capture_patched`, `capture_granularity`, `outcome_rules_installed`, `warnings`, `effective`). Body wrapped in fail-open guard (steps 3–6 never propagate; only pydantic validation of literal config args may raise): (1) build config; (2) guard; (3) `atm_capture.install_patches`; (4) self-test version ranges vs `atm_capture.compat.SUPPORTED_RANGES` + hook presence → loud warning naming offending package+version, never silently capture nothing; (5) install outcome patches via `atm_outcomes` (unresolved sdk_call → warning); (6) configure OTLP exporter (SecretStr, never logged).

**TDD:** `test_init_never_raises_into_host`; `test_ingest_key_never_in_repr` (+ no secret in caplog); `test_self_test_warns_on_incompatible_version`; `test_content_off_by_default`; `test_track_run_sets_active_run_id`; `test_scaffold_is_reversible` (byte-identical revert); e2e `test_init_to_cost_event` (one CostEvent; **H1: unrelated httpx client untouched**).

**pyproject:** hatchling, name `atm-margin`, deps atm-core/capture/outcomes + pydantic + opentelemetry-sdk + otlp-http exporter; ships `py.typed` inside `src/atm_margin/`. **Definition of Done:** init never raises into host; ingest key never in repr/log/dump; self-test warns with version; content off by default; track sets/resets active_run_id; scaffold byte-reversible; capture patch instance-scoped (H1).

#### [G3-TSSDK] — TypeScript SDK (`sdks/typescript`, `@atm-margin/sdk`)
**Depends on:** frozen `semconv.py`, G2 wire contract. **Blocks:** NPM-PKG, OTLP-CONTRACT TS half. **M9 framing:** `init()` is a **manual OpenTelemetry wrapper, NOT auto-instrumentation** — explicitly wraps the handed client instance (instance-scoped, mirroring H1), accumulates streaming tokens, emits ONE terminal cost span, installs OTLP/HTTP exporter.

**File tree:** dual ESM/CJS (`package.json` exports import/require/types; tsup builds ESM+CJS+`.d.ts`; tsconfig strict + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes`; eslint bans `any`). `src/{index,version,config,init,semconv,exporter,failOpen}.ts`, `src/instrument/{wrapOpenAI,wrapAnthropic,wrapVercelAi,streamAccumulator}.ts`, `src/cost/{tokenVector,priceBook}.ts`.

**`InitConfig`/`InitResult`** TS types (readonly; `client?: unknown` = instance to wrap, H1; `captureContent?` default false; ingestKey never logged). **streamAccumulator** mirrors Python terminal-value rule exactly: Anthropic output = terminal (never sum deltas); cache from message_start, NOT re-added from message_delta (the `@langchain/anthropic` 2× bug); OpenAI requires `stream_options.include_usage`; one span at stream end; cancelled → recover partial + tag, never zero silently.

**TDD (vitest):** `anthropicDeltaOutputOverwritten` (60 terminal not 95 sum); `cacheTokensNotDoubled`; `semconvKeysMatchPython` (vs generated fixture, no extra/missing); `initNeverThrowsIntoHost` (+ host call still succeeds); `selfTestWarnsOnVersion`; `streamingTerminalCostSpan` (exactly one span); `ingestKeyNotLogged` (only in outgoing header); H1 instance-scope (un-wrapped instance emits nothing).

**Definition of Done:** delta output overwritten not summed; cache not doubled; semconv keys match Python; init never throws into host; self-test warns with version; exactly one terminal span; ingest key never logged; instance-scoped; framed as manual OTel wrapper not auto-instrumentation.

#### [G3-OTLP-CONTRACT] — cross-language wire contract test (parallel, H3)
**Lives at:** `tests/wire_contract/` (+ generated fixture consumed by both sides). **Depends on:** frozen `semconv.py`; TS half lands with TSSDK.

`generate_semconv_fixture.py` imports `atm_capture.otlp.semconv.SEMCONV` → writes sorted `semconv_keys.json` (every gen_ai.* + ai_margin.* key). `sdks/typescript/test/fixtures/semconv_keys.json` is a copy/symlink. **TDD:** `test_wire_semconv_parity` (regenerate → byte-equal committed; CI runs generate then `git diff --exit-code` on both fixture copies BEFORE the TS job — non-empty diff fails build, H3); `test_ts_span_decodes_via_python` (load a TS-emitted span fixture → `span_to_cost_event` → valid CostEvent with terminal/un-doubled TokenVector, labeled provenance, populated ids).

**Definition of Done:** generated fixture == committed (drift fails CI); Py/TS key-sets identical; a TS-shaped span decodes into a valid CostEvent; turns `wire_semconv_parity` green.

#### [G3-PYPI-PKG] — Python packaging + clean-venv install proof
**Depends on:** PYSDK (green). Finalize `pyproject.toml` (hatchling; `py.typed` ships). `ci.yml` `pypi-publish` job: build artifact on PR; trusted-publish (OIDC, `id-token: write`, no stored token) on tag `v*`. **TDD (subprocess venv, never in-process):** `test_wheel_installs_in_clean_venv` (`uv build --wheel`, fresh venv, install wheel+deps, subprocess `import atm_margin; init(...)` exit 0; `py.typed` resolves); `test_twine_check_passes`; `test_sdist_contains_py_typed`. **Definition of Done:** wheel installs in clean subprocess venv and init works; twine check passes; py.typed in wheel+sdist; trusted-publish on tag only.

#### [G3-NPM-PKG] — npm packaging + dual ESM/CJS proof
**Depends on:** TSSDK (green). Finalize `package.json` (dual exports, `files:["dist"]`, `publishConfig.provenance`). `ci.yml` `npm-publish` job: pack on PR; `npm publish --provenance` (OIDC) on tag. **TDD (subprocess fixture):** `npmPackInstalls` (`tsup` build, `npm pack`, install tarball into fixture, `tsc --noEmit` passes); `dtsEmitted` (`dist/index.d.ts` has public surface, no `any`); `exportsResolveEsmAndCjs` (both `import` and `require` resolve `init`, run no-op). **Definition of Done:** pack output installs + type-checks under strict TS; `.d.ts` emitted; ESM+CJS both resolve+run; provenance publish on tag only.

---

### GROUP 4 — APPS (parallel; thin registry projections)

> **Cardinal rule (§3, §5):** apps are dumb projections — no app hand-writes a capability. Each iterates the registry, filters to its surface, and projects. `capability_on_every_declared_surface` asserts every capability appears on every surface it declares. Apps inject the concrete `atm_store` impl at the composition root (C3/H8); they depend on core ABCs + capabilities + each logic package's `register()`, never on internals. Excluded from coverage gate; projection-correctness tests must pass.

#### [G4-API] — FastAPI projection (`apps/api`)
`src/atm_api/{app.py, projection.py, auth.py, jobs.py, webhooks.py, errors.py}`. `mount_capabilities(app, registry, store)` iterates capabilities with `Surface.API`: request_response → `POST /{name}` whose body model IS `cap.input` and `response_model` IS `cap.output`; async_job → `POST` returns `{job_id}` + `GET /jobs/{id}` poll (never blocks); webhook_inbound → signature verified against RAW body bytes (HMAC-SHA256, constant-time) BEFORE parse + ingest key required. `auth.get_tenant` on every route (no unauthenticated capability route); handler passes tenant_id first to every repo call. **TDD:** every API capability becomes a route (and nothing without API does); tenant A cannot read tenant B (real Postgres testcontainers, 401 on bad auth); async_job uses job_id+poll (submit returns promptly); webhook signature verified on raw body (tampered → 401, handler not called; reserialized-JSON signature still rejected); rollup response carries both H7 fields (fake rollup omitting them rejected); request validation uses capability input model (422). **Green:** `capability_on_every_declared_surface` (API). **Definition of Done:** every API-declared capability projected and nothing else; tenant isolation on real PG; async_job poll pattern; raw-body signature verify; rollups carry H7; validation via capability input model.

#### [G4-MCP] — MCP server projection (`apps/mcp`)
`src/atm_mcp/{server.py, projection.py}`. For each `Surface.MCP` capability, register a tool: name=`cap.name`, description=`cap.description`, **inputSchema=`cap.input.model_json_schema()`** (generated, never hand-written); handler validates args, resolves tenant_id, calls handler. Includes `suggest_attribution_rule`/`validate_*`/`scaffold_*`. **TDD:** tool schema deep-equals input model json_schema; every MCP capability becomes a tool (none without); tool call tenant-scoped (only A's data, no-tenant rejected). **Definition of Done:** tool schemas equal capability input json_schema; every MCP-declared capability is a tool; calls tenant-scoped.

#### [G4-CLI] — CLI projection (`apps/cli`)
`src/atm_cli/{main.py, projection.py, render.py}`. For each `Surface.CLI` capability, a typer command with options from `cap.input`; tenant_id from required `--tenant`. **`render.py` MUST print `minimum_tier` on every rollup-returning command's output** (H7 — a number never renders without its confidence label) + the distribution. **TDD:** every CLI capability becomes a command (none without); rollup command prints minimum_tier + distribution (cannot print bare number); rollup command without `--tenant` errors. **Definition of Done:** every CLI-declared capability is a command; rollups always print minimum_tier; tenant scope required.

#### [G4-NOTIFY] — notification sinks (`apps/notify`)
`src/atm_notify/{models.py, builder.py, correction.py, sinks/{slack,email}.py, register.py}`. **No raw content ever.** `DigestMetric` (frozen/forbid/strict): `name, value: Decimal, unit, minimum_tier: BindingTier` (REQUIRED H7), `confidence_distribution: dict[BindingTier,int]` (REQUIRED H7), `provenance_breakdown: dict[Provenance,Decimal]` (§5.3a), `pct_unallocated: Decimal|None`; model_validator denies fields named raw/prompt/response/email/customer_id/user_id (+ `notify_aggregate_only` static scan). `Digest` (tenant_id, period, metrics, `corrections`, generated_at). `Correction` (metric_name, previous_value, corrected_value, `reason: Literal["outcome_retracted"]`, affected_outcome_id). `builder` reads rollups ONLY via capabilities; aggregate + minimum_tier only; a `minimum_tier` display filter, but surviving metrics STILL carry their own label (never collapsed). `correction` (H8): retracted outcome → next cycle recomputes (removed from denominator) + emits a `Correction`. **TDD:** digest model forbids raw/PII (extra=forbid + denylist); DigestMetric requires both H7 fields; builder aggregates only (1 exact + 50 candidate → minimum_tier candidate, distribution {exact:1,candidate:50}, not collapsed; no raw field); minimum_tier filter preserves per-metric labels; retracted outcome corrected next cycle. **Green:** `notify_aggregate_only`. **Definition of Done:** digest models forbid raw/PII; DigestMetric requires both H7 fields; builder never collapses distribution; minimum_tier filter preserves labels; retraction → correction next cycle.

#### [G4-AGENT-INTEGRABILITY] — agent integration surface (`apps/agent_integrability`)
`src/atm_agent_integrability/{llms_txt.py, agents_md_writer.py, scaffold_caps.py, skill/SKILL.md}` + `examples/{fastapi,django,express,langchain,stripe_t3}/outcomes.yaml`. `generate_llms_txt(registry)` lists EVERY capability + an `instructions:` section correcting model priors (binding tier system-owned, signal_class system-mapped, use `suggest_attribution_rule` not guessing). `write_agents_md(user_repo)` writes a snippet INTO the user's repo (agents don't scan site-packages). `scaffold_caps` registers `scaffold_outcome_rule`/`validate_outcome_rule`/`validate_init`/`suggest_attribution_rule` (surfaces incl MCP); scaffold/suggest returns a DRAFT marked unconfirmed/candidate (human confirms, never auto-applied). `SKILL.md` = scan→propose→wire→validate→hand-off-as-diff. **TDD:** all example outcomes.yaml validate (incl stripe_t3 run_id_injection); llms.txt lists every capability + has instructions section asserting system-owned axes; scaffold/suggest returns unconfirmed candidate (not auto-applied); AGENTS.md written into user repo; SKILL.md references validate tools. **Definition of Done:** all shipped examples validate; llms.txt complete + instructions section; scaffold/suggest unconfirmed; AGENTS.md in user repo; Skill references validate tools.

---

### GROUP 5 — INTEGRATION + E2E + CONFORMANCE BARRIER (serial; Definition-of-Done gate)

> This is the only place real wiring + real Postgres + real cross-language OTLP run. Nothing mocks the store or wire path. **The build is DONE only when every G5 task is green.** Real-Postgres rule (H2): every storage-touching test runs against a real Postgres (testcontainers), no SQLite for JSONB, no mocks; shared session-scoped container, per-test fresh schema/transaction rollback.

#### [G5-INTEGRATION] — cross-package flows on real Postgres
`tests/integration/` with `conftest.py` (session-scoped Postgres; real `atm_store` migrations applied — never autogenerate; `StoreBundle` of concrete repos; `Registry` via `discover_and_register([capture,outcomes,attribution,reconciliation,allocation,eval,metrics,onboarding,notify])`; deterministic Clock/UuidGen; TENANT_A/TENANT_B). **Tests:** `test_capture_to_store_to_metrics` (rollup totals == summed cost_usd, provenance preserved + aggregated, H7 fields present; duplicate (run_id,attempt_id) doesn't double-count); `test_outcomes_attribution_store_metrics` (T1 ambient→exact, T3 round-trip→deterministic, T4 entity→candidate review-queued + excluded from billing denominator; candidate/likely excluded from denominator but counted); `test_reconciliation_trueup_then_query` (per-attempt reconciled deltas sum EXACTLY to billed total, Decimal no drift; estimate row UNCHANGED + separate additive ReconciliationRecord; mixed reconciled/provisional/estimate_only window carries provenance_breakdown); `test_allocation_rollup` (Tier-1 measured + Tier-2 allocated labeled + split sums exactly + idle GPU Tier-3 quarantined beside not smeared + pct_unallocated; absent yaml → Tier-1-only with pct_unallocated prominent); `test_eval_funnel` (discover by tool-set fingerprint; smoke eliminates >25% no CI; recommendation requires 95% CI separation, None when nothing separates; report JSON source of truth carries auto_switch==False, label_source rung, reliable/directional grade capped at directional for counterfactual outcomes, latency p50/p95/p99, Pareto, disagreements, gap_distribution); `test_tenant_isolation_no_leakage` (every read capability A↔B returns zero cross-tenant; every repo method invoked with tenant_id first); `test_retraction_removes_from_denominator` (retracted removed + metric re-emitted/annotated H8). **Definition of Done:** all five core flows work on real Postgres; idempotent upserts never double-count; reconciliation additive + prorations sum exactly; allocation labels/quarantines; eval honors grade caps + CI gates + auto_switch=False; zero cross-tenant leakage; retraction removes + re-emits.

#### [G5-E2E-CROSS-LANG] — real cross-language OTLP e2e
`tests/e2e/` with `conftest.py` (real Postgres + real `atm_api` OTLP ingest endpoint up) + `helpers/run_ts_producer.ts`. **Tests:** `test_ts_init_to_python_store_e2e` (run built TS SDK in subprocess → `init()` against live endpoint → one streamed Anthropic-shaped call → ONE OTLP span to Python ingest → assert exactly one CostEvent row in Postgres with **terminal** output (not summed) + **un-doubled** cache + cost_usd non-None + labeled provenance + populated ids/tenant); `test_python_init_to_store_e2e` (Python init → fake call → one stored CostEvent; H1 unrelated httpx client → no event); `test_no_secret_anywhere_in_run` (sentinel ingest key `"sk-SENTINEL-DO-NOT-LEAK"` + sentinel provider key for eval; after a full Py+TS run assert the sentinel appears in NONE of: any span attribute (in-flight or persisted), any log line (all loggers + subprocess stdout/stderr), any Postgres row/column (every text/JSONB column) — the ONLY permitted location is the in-flight OTLP Authorization header). **Definition of Done:** TS-produced span ingests into Python and stores correct terminal/un-doubled tokens; Python init produces stored CostEvent; sentinel appears in no span attr / no log / no DB row (only in-flight header).

#### [G5-CONFORMANCE-GREEN] — final barrier (the Definition-of-Done gate)
`tests/conformance/{static,behavioral}/` per §3. Runs the FULL suite against the complete repo; **every rule must be green.** Key concretizations: `no_auto_switch` (behavioral — no path applies a switch without explicit human→canary→auto-rollback; artifact `auto_switch==False`); `no_secret_logging` (the G5 runtime sentinel test as a gate); `grade_cap_invariant` (reliable only from outcome_label on reconstructable task OR human labels TPR/TNR≥0.9 against committed N≥50 fixture; counterfactual/delayed capped directional; switch only when `|new-old|/|old|≥0.15`); `migration_no_autogen_drift` (autogenerate → empty diff); `rollup_carries_confidence` (every rollup output has both H7 fields + property test: aggregation never raises confidence). **Repo-wide gates (all pass):** pyright `--strict` clean repo-wide (`reportUnnecessaryTypeIgnoreComment=error`); ruff check + format clean; `tsc --strict` + eslint clean for TS; coverage ≥90% line+branch on EVERY core logic package (`atm_core, atm_capture, atm_outcomes, atm_attribution, atm_reconciliation, atm_allocation, atm_eval, atm_metrics, atm_store, atm_onboarding`); import-linter contracts pass (deps flow toward core, no cycles). **Definition of Done (the build is DONE only when all hold):** every conformance rule green (static + behavioral, split per H4); pyright/ruff clean repo-wide; tsc/eslint clean for TS; ≥90% coverage on every core logic package; import-linter passes; cross-language e2e green; sentinel secret appears in no span attribute, no log, no DB row. **Until this task is green, the build is not done.**

---

## 5. COVERAGE CHECKLIST (design component → task; H10 owners marked)

| Design component | Owning task(s) |
|---|---|
| Three honesty axes (Provenance, BindingTier, SignalClass) | F0-CORE-1a (enums), F0-CONFORMANCE (axes invariants), G1-EXIT meta-test #4 |
| `TokenVector` six invariants (§5.2) | F0-CORE-1a; capture warning path G2-CAPTURE/PG1 |
| `ProvenanceLabel` link rules | F0-CORE-1a |
| Domain events (Cost/Outcome/Run/Attribution/Recon/Alloc) | F0-CORE-1b |
| H7 conservative propagation (RollupConfidence, compose_label) | F0-CORE-1b (rollup.py); carried by ALLOC, METRICS, NOTIFY, dry-run |
| Repository ABCs (tenant_id first, recon append-only) | F0-CORE-1c; concrete impls G2-STORE |
| Capability registry + Surface(incl NOTIFY)/Mode | F0-CAPS |
| Conformance harness (static + behavioral, H4) | F0-CONFORMANCE-SKELETON; final G5-CONFORMANCE-GREEN |
| Context propagation, ThreadPool copy_context, **fork-degrade (H10)** | G1-CORE-CONTEXT (provides `run_in_context`); SDK patches submit G3-PYSDK; fork-degrade tested G2-ATTRIBUTION/G3 |
| Eval models, `auto_switch=Literal[False]`, ProviderKeyRef (no plaintext) | G1-CORE-EVAL |
| Pricing (PriceCard/PriceBook, OpenAI no cache-write) | G1-CORE-CAPTURE-FIELDS; compute G2-CAPTURE/PG1 |
| Webhook result, ReviewQueue, C3 Protocols | G1-CORE-OUTCOMES-ATTR |
| Instance-scoped transport patch (H1) | G2-CAPTURE/PG2; SDK façades G3-PYSDK/TSSDK |
| Fail-open guard + bounded emit | G2-CAPTURE/PG0 |
| Streaming terminal-value (2× cache bug, no-delta-sum) | G2-CAPTURE/PG3; TS mirror G3-TSSDK |
| OTLP wire contract (semconv single source, H3) | G2-CAPTURE/PG4; parity G3-OTLP-CONTRACT |
| OpenRouter authoritative inline; **PTU refusal cost_usd=None (H10)** | G2-CAPTURE/PG5 (provider_costapi/gateway) |
| outcomes.yaml grammar + safe loader (no eval) | G2-OUTCOMES/OUT-A |
| Function patch + SignalClassMapper (signal never user-set) | G2-OUTCOMES/OUT-B |
| **T3 run_id injection, copy-on-write, init-ordering warn (H10)** | G2-OUTCOMES/OUT-C |
| Webhook ingest (verify-before-parse, T3 echo / T4 fallback) | G2-OUTCOMES/OUT-D |
| Retraction (confirmed→retracted, H8) | G2-OUTCOMES/OUT-E; denominator effect G2-METRICS; correction G4-NOTIFY |
| Binding cascade T1→T5 + fast-path revalidation + ambiguity halt | G2-ATTRIBUTION |
| System-owned confidence map | G2-ATTRIBUTION/ATTR-0 |
| All migrations + table schemas (C2 sub-barrier) | G2-STORE/STORE-1 |
| Concrete tenant-scoped repos + idempotent upsert + JSONB fidelity | G2-STORE/STORE-2/3/4 |
| **GDPR erasure (erase_by_entity, H10)** | F0-CORE-1c (ABC); concrete G2-STORE |
| Reconciliation true-up (proration ROUND_HALF_EVEN, additive, manual CSV, drift) | G2-RECON |
| Three-tier allocation (DIRECT/SHARED/FIXED), pct_unallocated, idle-GPU quarantine | G2-ALLOC |
| Metric typed mini-DSL (closed allowlist, no SQL/eval) + H7/H8 propagation | G2-METRICS |
| Eval funnel (discover→dataset→grade→search→costgate→report→cadence) | G2-EVAL |
| **Two-phase cost gate; provider tokenizer not tiktoken; key never persisted (H10)** | G2-EVAL/costgate |
| Grade caps + CI gates + triggered cadence (no timer) | G2-EVAL |
| Onboarding scan→propose→validate→render→diff→dryrun | G2-ONBOARDING |
| **suggest_attribution_rule (drafts unconfirmed, H10)** | G2-ONBOARDING/suggest + G4-AGENT-INTEGRABILITY/scaffold_caps |
| Secret redaction + reviewable-diff (hunks-only) + read-only GitHub App (H12) | G2-ONBOARDING |
| Python SDK one-line init (façade, fail-open) | G3-PYSDK |
| TS SDK manual OTel wrapper (M9) | G3-TSSDK |
| Cross-language wire parity (H3) | G3-OTLP-CONTRACT |
| PyPI / npm packaging (clean-install + dual ESM/CJS proofs) | G3-PYPI-PKG / G3-NPM-PKG |
| API / MCP / CLI / NOTIFY projections (registry-driven) | G4-API/MCP/CLI/NOTIFY |
| llms.txt + AGENTS.md-into-user-repo + onboarding Skill + examples | G4-AGENT-INTEGRABILITY |
| Real cross-package + cross-language integration on real Postgres | G5-INTEGRATION / G5-E2E-CROSS-LANG |
| Definition-of-Done conformance + repo-wide gates | G5-CONFORMANCE-GREEN |

**H10 newly-assigned owners (explicit):** PTU/billing-uncertain `cost_usd=None` refusal → **G2-CAPTURE/PG5 (provider_costapi)** with the field defined at **F0-CORE-1b**; ThreadPool copy_context + fork-degrade + baggage → **G1-CORE-CONTEXT** (provides `run_in_context`), patched by **G3-PYSDK**, fork-degrade tested at **G2-ATTRIBUTION/G3**; T3 run_id injection init-ordering warning → **G2-OUTCOMES/OUT-C**; GDPR `erase_by_entity` → ABC at **F0-CORE-1c**, concrete at **G2-STORE**; eval two-phase gate + provider-tokenizer (no tiktoken) + provider key never persisted → **G2-EVAL/costgate**; `suggest_attribution_rule` drafts-unconfirmed → **G2-ONBOARDING/suggest** surfaced as a capability by **G4-AGENT-INTEGRABILITY**.

---

## 6. PER-TASK DEFINITION-OF-DONE (consolidated)

| Task | Definition of Done |
|---|---|
| **F0-TOOLING** | `uv sync` exit 0 + lockfile resolves; pyright/ruff/lint-imports exit 0 on empty skeletons; coverage gate=90 branch-on; `atm_` prefix locked by test; CI file present (jobs red until later groups OK). |
| **F0-CORE-1a** | enum values exact; tenant required + naive datetime rejected; frozen+forbid+strict; TokenVector six invariants + from_provider guard; ProvenanceLabel link rules both directions; pyright/ruff clean. |
| **F0-CORE-1b** | idempotency keys correct; is_billing_grade exact/deterministic only; recon additive (no mutate field); AllocatedLine consistency; minimum_tier==least-trusted present; both H7 fields round-trip. |
| **F0-CORE-1c** | every abstractmethod tenant_id-first (AST); recon no update/replace/mutate; all 7 ABCs exported. |
| **F0-CORE-INIT** | core suite green; pyright/ruff clean; ≥90% on atm_core; explicit complete `__all__`. |
| **F0-CAPS** | Surface incl NOTIFY + four Modes; dup-name hard error; webhook≠CLI; discover raises on missing register; import set ⊆ {stdlib,pydantic,typing}. |
| **F0-CONFORMANCE-SKELETON** | each rule flags its negative fixture AND passes foundation; foundation rules green now; rest skip-marked with owning task ID; static/behavioral split proven. |
| **G1-CORE-CONTEXT** | active_run_id default None; run_in_context carries across thread (raw submit does not); Protocols runtime_checkable. |
| **G1-CORE-EVAL** | auto_switch Literal[False]; ProviderKeyRef no plaintext field; reliable requires outcome/human label; recommended None valid. |
| **G1-CORE-RECON-ALLOC** | AllocatedRollup carries both H7 fields; pct_unallocated present; provenance_breakdown sums; DriftAlert ranks causes. |
| **G1-CORE-CAPTURE-FIELDS** | PriceCard per-token-class; OpenAI no cache-write modeled; PriceBook picks effective card by date. |
| **G1-CORE-OUTCOMES-ATTR** | WebhookResult verified flag; SignalClassMapper runtime_checkable; ReviewQueue tenant-first; predicate validator present. |
| **G1 EXIT BARRIER** | all 7 EXIT meta-tests green (frozen/forbid/strict; events tenant-scoped; repos tenant-first full set; EvalGrade/ReconState not event fields; every rollup both H7 fields; config allowlist fixed; ≥90% core coverage). No G2 starts until green. |
| **G2-STORE** | all 8 tables + migrations published before store-touching G2 work; 7 repos tenant-scoped; money NUMERIC(20,10) no float; recon append-only; JSONB byte-fidelity on real PG; idempotent upserts; autogenerate empty diff; ≥90%. |
| **G2-CAPTURE** | PG0–PG5 sub-barriers green; H1 instance-scope proven (unrelated httpx untouched); fail-open proven; streaming terminal/un-doubled; semconv fixture committed; PTU refusal; ends register; ≥90%. |
| **G2-OUTCOMES** | OUT-A→E green; predicates safe (no eval); signal system-owned (function/http never confirmed); secrets never logged; copy-on-write injection + init-order warn; ends register; ≥90%. |
| **G2-ATTRIBUTION** | cascade short-circuits + fast-path revalidates dangling + halts on ambiguity; candidate/likely always review + never billing-grade; confidence map system-owned; ends register; ≥90%. |
| **G2-RECON** | prorations sum exactly (Decimal half-even); additive never mutates estimate; drift ranked at 10% boundary; manual CSV labeled; mixed-state breakdown carried; provider key never logged; ends register; ≥90%. |
| **G2-ALLOC** | three-tier split sums exactly; idle GPU quarantined beside (not smeared); pct_unallocated surfaced; H7 fields present; ends register; ≥90%. |
| **G2-METRICS** | DSL closed-allowlist + no eval/SQL; compiler pure; minimum_tier==min; candidate/likely excluded-but-counted; retracted excluded + re-emitted; ends register; ≥90%. |
| **G2-EVAL** | full funnel green over fakes + repo-ABC stub; grade caps + 95%-CI gate + smoke-no-CI + auto_switch=False; no tiktoken; two-phase gate ordered; sentinel key never leaks; ends register; ≥90%. |
| **G2-ONBOARDING** | scan read-only + secret-safe; proposals system-mapped + T3/T4 labeled; diff hunks-only no secrets; github app no exfil path + scope-limited; suggest returns unconfirmed; dry-run carries H7; ends register; ≥90%. |
| **G3-PYSDK** | init never raises into host; ingest key never in repr/log/dump; self-test warns with version; content off by default; track sets/resets active_run_id; scaffold byte-reversible; patch instance-scoped (H1). |
| **G3-TSSDK** | delta output overwritten not summed; cache not doubled; semconv keys match Python; init never throws into host; self-test warns; exactly one terminal span; ingest key never logged; instance-scoped; manual-OTel framing. |
| **G3-OTLP-CONTRACT** | generated fixture == committed (drift fails CI); Py/TS key-sets identical; TS-shaped span decodes to valid CostEvent; `wire_semconv_parity` green. |
| **G3-PYPI-PKG** | wheel installs in clean subprocess venv + init works; twine check passes; py.typed in wheel+sdist; trusted-publish on tag only. |
| **G3-NPM-PKG** | pack installs + type-checks under strict TS; .d.ts emitted (no any); ESM+CJS both resolve+run; provenance publish on tag only. |
| **G4-API** | every API capability projected and nothing else; tenant isolation on real PG; async_job poll; raw-body signature verify before parse; rollups carry both H7 fields; validation via capability input model. |
| **G4-MCP** | tool schemas equal capability input json_schema; every MCP capability is a tool; calls tenant-scoped. |
| **G4-CLI** | every CLI capability is a command; rollups always print minimum_tier + distribution; tenant scope required. |
| **G4-NOTIFY** | digest models forbid raw/PII; DigestMetric requires both H7 fields; builder never collapses distribution; minimum_tier filter preserves labels; retraction → correction next cycle. |
| **G4-AGENT-INTEGRABILITY** | all example outcomes.yaml validate; llms.txt lists every capability + instructions section asserting system-owned axes; scaffold/suggest unconfirmed; AGENTS.md in user repo; Skill references validate tools. |
| **G5-INTEGRATION** | all five core flows on real Postgres; idempotent upserts never double-count; reconciliation additive + sums exactly; allocation labels/quarantines; eval grade-caps + CI gates + auto_switch=False; zero cross-tenant leakage; retraction removes + re-emits. |
| **G5-E2E-CROSS-LANG** | TS-produced span ingests into Python + stores correct terminal/un-doubled tokens; Python init produces stored CostEvent; sentinel appears in no span attr / no log / no DB row (only in-flight header). |
| **G5-CONFORMANCE-GREEN** | every conformance rule green (static + behavioral); pyright/ruff clean repo-wide; tsc/eslint clean for TS; ≥90% coverage on every core logic package; import-linter passes; cross-language e2e green. **Until green, the build is not done.** |