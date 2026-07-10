/**
 * Onboarding scan types — mirror the Python `valuemaxx.onboarding.capabilities` shapes so
 * the TS scanner emits the same `ScanResult` the Python one does (a parity test enforces it).
 */

/** The kind of a detected site (same literal set as Python's `SiteKind`). */
export type SiteKind =
  "run_boundary" | "status_setter" | "mark_function" | "external_write" | "webhook_handler";

/** One detected site: a run boundary or an outcome site. Mirrors Python `ScanSite`. */
export interface ScanSite {
  readonly kind: SiteKind;
  readonly file: string;
  readonly line: number;
  readonly symbol: string;
  readonly snippet: string;
  readonly system: string | null;
  readonly echoesMetadata: boolean;
  readonly entityIds: readonly string[];
}

/** The result of scanning a codebase. Mirrors Python `ScanResult`. */
export interface ScanResult {
  readonly runBoundaries: readonly ScanSite[];
  readonly outcomeSites: readonly ScanSite[];
  readonly entityIds: readonly string[];
  readonly warnings: readonly string[];
}

/** The cross-language rule set, loaded from tests/wire_contract/onboarding_rules.json. */
export interface OnboardingRules {
  readonly ts_llm_calls: readonly string[];
  readonly ts_provider_calls: readonly string[];
  readonly orm_writes: readonly string[];
  readonly mark_prefixes: readonly string[];
  readonly ts_suffixes: readonly string[];
  readonly echoing_systems: readonly string[];
  readonly external_systems: Readonly<Record<string, string>>;
  readonly ignored_dirs: readonly string[];
  readonly entity_id_exclusions: readonly string[];
  readonly redaction_placeholder: string;
  readonly redact_prefix_patterns: readonly string[];
  readonly redact_secret_name_alt: string;
  readonly redact_high_entropy_pattern: string;
  readonly redact_high_entropy_bits: number;
}
