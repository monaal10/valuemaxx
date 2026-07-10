/**
 * Render — the `outcomes.yaml` body for a proposal. TS mirror of Python
 * `valuemaxx.onboarding.render`. The Python side and this one produce YAML with the same
 * semantic CONTENT (the golden parity test compares the PARSED documents, not exact bytes —
 * `outcomes.yaml` is consumed via `yaml.safe_load`, so content, not whitespace, is the
 * contract). Deterministic: rules stable-sorted by name, keys in a fixed order, no
 * timestamps, every string re-redacted.
 */

import { stringify } from "yaml";

import { redact } from "./redact.js";
import type { OnboardingRules } from "./types.js";
import type { OutcomeRuleCandidate, Proposal } from "./propose.js";

/** The ordered, redacted plain object for one outcome rule (matches Python key set). */
function ruleMapping(rule: OutcomeRuleCandidate, rules: OnboardingRules): Record<string, unknown> {
  const mapping: Record<string, unknown> = {
    name: redact(rule.name, rules),
    match_kind: rule.matchKind,
    match_target: redact(rule.matchTarget, rules),
    when: redact(rule.when, rules),
    signal: rule.signal,
    tier: rule.tier,
  };
  if (rule.runIdInjection !== null) {
    const inj = rule.runIdInjection;
    mapping["run_id_injection"] = {
      system: redact(inj.system, rules),
      target_field: redact(inj.targetField, rules),
      write_site: redact(inj.writeSite, rules),
    };
  }
  if (rule.warnings.length > 0) {
    mapping["warnings"] = rule.warnings.map((w) => redact(w, rules));
  }
  return mapping;
}

/**
 * Render the `outcomes.yaml` body for `proposal`. Rules are stable-sorted by name and the
 * top-level keys sorted, so re-rendering an unchanged proposal is byte-stable within this
 * serializer (a clean review diff); the cross-language contract is the parsed content.
 */
export function renderOutcomesYaml(proposal: Proposal, rules: OnboardingRules): string {
  const sortedRules = [...proposal.rules].sort((a, b) =>
    a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
  );
  const payload = {
    version: 1,
    outcomes: sortedRules.map((r) => ruleMapping(r, rules)),
    entity_ids: [...proposal.entityIds]
      .map((e) => redact(e, rules))
      .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0)),
  };
  // sortMapEntries mirrors PyYAML's sort_keys=True (alphabetical keys); block style.
  return redact(stringify(payload, { sortMapEntries: true }), rules);
}
