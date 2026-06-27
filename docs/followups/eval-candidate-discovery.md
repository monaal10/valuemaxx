# Follow-up (optional): auto-discover eval candidate models (the $0-prune)

**v1 decision:** valuemaxx runs on **user-supplied candidate models** — you name the
3–8 models to compare against your incumbent, and valuemaxx runs the rigorous
eval + cheaper-at-parity recommendation on them. This is the intended v1 behavior,
not a bug. Auto-discovery (below) is an OPTIONAL future enhancement, not required.

## The gap
`packages/eval/src/valuemaxx/eval/search.py` RANKS candidate models rigorously —
`smoke_eval` (drop underperformers vs incumbent, keep top-3) → `confirmation_eval`
+ `pick_winner` (parity ≥ incumbent AND 95% CI separates → lowest-cost winner) →
`pareto_frontier` (cost×quality×latency, dominated points flagged, OSS fully-loaded
costed). This is the built, tested logic.

But `smoke_eval`/`confirmation_eval` take an already-chosen `Sequence[CandidateScore]`.
The design's "$0 priors prune 100 → 3–8" (task-matched leaderboards, drop
Pareto-dominated, your own logs) is described in the design doc §8.4 but the live
code does NOT auto-assemble the candidate pool. Today the *caller* names the 3–8
candidates to compare; valuemaxx then evals + recommends the cheaper-at-parity one.

## To close it (when picked up)
- A model catalog: per-provider price/tier/latency (a maintained table, à la the
  pricebook the capture side already has).
- A `select_candidates(incumbent, task_type, catalog) -> list[ModelCandidate]`
  that returns cheaper models in the same/adjacent capability tier, dropping
  Pareto-dominated ones — feeding the existing smoke→confirm→Pareto pipeline.
- Honest caveat: leaderboard priors predict, never substitute for the on-your-data
  eval (which is the whole point); the catalog perishability is handled by the
  new-model-release cadence trigger that already exists.

Until built, the README/eval docs should say: valuemaxx runs the rigorous
eval + recommendation on the candidate models YOU choose to compare.
