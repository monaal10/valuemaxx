/**
 * Propose — turn a scan into UNCONFIRMED candidate outcome rules. The TS mirror of Python
 * `valuemaxx.onboarding.propose` (a golden parity test asserts the two produce the same
 * proposal). The signal class is SYSTEM-owned (a bare external write is only
 * `action_attempted`; an in-process status/mark/ORM write, a webhook, confirm an outcome) —
 * never user-set, so a function attempt can never masquerade as a confirmed outcome.
 */

import { redact } from "./redact.js";
import type { OnboardingRules, ScanSite } from "./types.js";

type MatchKind = "status_setter" | "mark_function" | "orm_write" | "external_write" | "webhook";
type BindingTier = "exact" | "deterministic" | "candidate" | "likely";
type SignalClass = "action_attempted" | "outcome_confirmed";

export interface RunIdInjection {
  readonly system: string;
  readonly targetField: string;
  readonly writeSite: string;
}

export interface OutcomeRuleCandidate {
  readonly name: string;
  readonly matchKind: MatchKind;
  readonly matchTarget: string;
  readonly when: string;
  readonly signal: SignalClass;
  readonly tier: BindingTier;
  readonly runIdInjection: RunIdInjection | null;
  readonly warnings: readonly string[];
}

export interface Proposal {
  readonly rules: readonly OutcomeRuleCandidate[];
  readonly entityIds: readonly string[];
  readonly sharedCostsPresent: boolean;
  readonly warnings: readonly string[];
}

const SITE_TO_MATCH: Record<string, MatchKind> = {
  status_setter: "status_setter",
  mark_function: "mark_function",
  orm_write: "orm_write",
  external_write: "external_write",
  webhook_handler: "webhook",
};

// Site kinds that bind synchronously in-process (exact).
const IN_PROCESS_KINDS = new Set(["status_setter", "mark_function", "orm_write"]);

// Match kinds whose signal is a CONFIRMED outcome (system-owned; mirrors the Python mapper).
const CONFIRMING = new Set<MatchKind>(["status_setter", "mark_function", "orm_write", "webhook"]);

// The run-id metadata field injected into an echoing system's outbound object.
const INJECTED_FIELD = "metadata.atm_run_id";

function signalFor(site: ScanSite): SignalClass {
  return CONFIRMING.has(SITE_TO_MATCH[site.kind]!) ? "outcome_confirmed" : "action_attempted";
}

function defaultWhen(site: ScanSite): string {
  if (site.kind === "status_setter") return "args.status != None";
  if (site.kind === "webhook_handler") return "event.type != None";
  return "True";
}

function ruleForSite(site: ScanSite, rules: OnboardingRules): OutcomeRuleCandidate {
  const matchKind = SITE_TO_MATCH[site.kind]!;
  const signal = signalFor(site);
  let tier: BindingTier;
  let injection: RunIdInjection | null = null;
  let warnings: string[] = [];

  if (IN_PROCESS_KINDS.has(site.kind)) {
    tier = "exact";
  } else if (site.kind === "webhook_handler") {
    tier = "deterministic";
  } else if (site.kind === "external_write" && site.echoesMetadata) {
    tier = "deterministic";
    injection = {
      system: redact(site.system ?? "unknown", rules),
      targetField: INJECTED_FIELD,
      writeSite: redact(site.symbol, rules),
    };
  } else {
    // non-echoing external write
    tier = "candidate";
    const system = redact(site.system ?? "unknown", rules);
    warnings = [
      `${system} does not echo injected metadata; deterministic T3 binding is ` +
        `unavailable. Falling back to entity-id matching (candidate/T4); a human ` +
        `must confirm before this is trusted.`,
    ];
  }

  return {
    name: redact(site.symbol, rules),
    matchKind,
    matchTarget: redact(`${site.file}:${site.symbol}`, rules),
    when: redact(defaultWhen(site), rules),
    signal,
    tier,
    runIdInjection: injection,
    warnings,
  };
}

/** Build a reviewable proposal of UNCONFIRMED candidate rules from a scan. */
export function buildProposal(
  scan: {
    outcomeSites: readonly ScanSite[];
    entityIds: readonly string[];
    warnings: readonly string[];
  },
  rules: OnboardingRules,
): Proposal {
  return {
    rules: scan.outcomeSites.map((s) => ruleForSite(s, rules)),
    entityIds: scan.entityIds.map((e) => redact(e, rules)),
    sharedCostsPresent: false,
    warnings: scan.warnings.map((w) => redact(w, rules)),
  };
}
