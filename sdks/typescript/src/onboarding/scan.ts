/**
 * TS/JS onboarding scanner — the TS mirror of Python `valuemaxx.onboarding.ts_scan`.
 *
 * Parses each source file with the TypeScript compiler (an AST, never executing the code)
 * and emits the same `ScanSite` shape the Python scanner does, driven by the shared rules
 * contract (`onboarding_rules.json`). A parity test runs a fixture repo through both and
 * diffs the result, so the two scanners cannot drift.
 *
 * What it finds (Vercel-AI-SDK-style code):
 *  - run boundaries — `generateText`/`streamText`/… and provider setup `createOpenAI`/…;
 *  - outcome sites — ORM writes (`.save()`/…), `mark*`/`resolve`/… calls, `.status = …`
 *    setters, and outbound calls to known echoing systems (Stripe/HubSpot/…);
 *  - entity ids in scope — `*Id` / `*_id` identifiers.
 * Every captured string passes {@link redact}.
 */

import ts from "typescript";

import { redact } from "./redact.js";
import type { OnboardingRules, ScanSite, SiteKind } from "./types.js";

/** The simple name being called: `foo(...)` -> `foo`; `a.b.foo(...)` -> `foo`. */
function calleeName(call: ts.CallExpression): string | null {
  const fn = call.expression;
  if (ts.isIdentifier(fn)) return fn.text;
  if (ts.isPropertyAccessExpression(fn)) return fn.name.text;
  return null;
}

/** Best-effort name of the function/method enclosing `node` (for the site symbol). */
function enclosingSymbol(node: ts.Node): string {
  let cur: ts.Node | undefined = node.parent;
  while (cur) {
    if (
      (ts.isFunctionDeclaration(cur) || ts.isMethodDeclaration(cur)) &&
      cur.name &&
      ts.isIdentifier(cur.name)
    ) {
      return cur.name.text;
    }
    if (
      ts.isVariableDeclaration(cur) &&
      cur.initializer &&
      (ts.isArrowFunction(cur.initializer) || ts.isFunctionExpression(cur.initializer)) &&
      ts.isIdentifier(cur.name)
    ) {
      return cur.name.text;
    }
    cur = cur.parent;
  }
  return "<module>";
}

/** If the call's receiver names a known echoing system, return it (stripe/…). */
function systemForCall(call: ts.CallExpression, rules: OnboardingRules): string | null {
  const fn = call.expression;
  if (!ts.isPropertyAccessExpression(fn)) return null;
  const receiver = fn.expression.getText().toLowerCase();
  for (const system of rules.echoing_systems) {
    if (receiver.includes(system)) return system;
  }
  return null;
}

function site(
  kind: SiteKind,
  file: string,
  node: ts.Node,
  sourceFile: ts.SourceFile,
  rules: OnboardingRules,
  system: string | null = null,
): ScanSite {
  const { line } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
  return {
    kind,
    file,
    line: line + 1, // 1-based, like Python
    symbol: redact(enclosingSymbol(node), rules),
    snippet: redact(node.getText(sourceFile), rules).slice(0, 200),
    system,
    echoesMetadata: system !== null && rules.echoing_systems.includes(system),
    entityIds: [],
  };
}

/** Collect `*Id` / `*_id` identifiers used in the file (in-scope entity keys). */
function entityIdsInFile(sourceFile: ts.SourceFile, rules: OnboardingRules): string[] {
  const ids: string[] = [];
  const exclusions = new Set(rules.entity_id_exclusions);
  const visit = (node: ts.Node): void => {
    if (ts.isIdentifier(node)) {
      const name = node.text;
      const low = name.toLowerCase();
      const looksLikeId = (low.endsWith("id") && name.length > 2) || low.endsWith("_id");
      if (looksLikeId && !ids.includes(name) && !exclusions.has(name)) ids.push(name);
    }
    ts.forEachChild(node, visit);
  };
  ts.forEachChild(sourceFile, visit);
  return ids;
}

/**
 * Scan one TS/JS source string. Returns run boundaries, outcome sites, and entity ids —
 * the same triple the Python `scan_ts_source` returns. Never throws on a parse error.
 */
export function scanTsSource(
  text: string,
  file: string,
  rules: OnboardingRules,
): { runBoundaries: ScanSite[]; outcomeSites: ScanSite[]; entityIds: string[] } {
  const runBoundaries: ScanSite[] = [];
  const outcomeSites: ScanSite[] = [];

  const sourceFile = ts.createSourceFile(
    file,
    text,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );

  const llmCalls = new Set(rules.ts_llm_calls);
  const providerCalls = new Set(rules.ts_provider_calls);
  const ormWrites = new Set(rules.orm_writes);

  // Match the Python scanner's traversal EXACTLY: a LIFO stack (push children, pop) — not a
  // pre-order forEachChild — so the two emit sites in the same order (the render sort is by
  // name only and stable, so same-name ties must resolve identically across languages).
  const stack: ts.Node[] = [sourceFile];
  while (stack.length > 0) {
    const node = stack.pop()!;
    if (ts.isCallExpression(node)) {
      const name = calleeName(node);
      if (name !== null && (llmCalls.has(name) || providerCalls.has(name))) {
        runBoundaries.push(site("run_boundary", file, node, sourceFile, rules));
      } else if (name !== null && ormWrites.has(name)) {
        outcomeSites.push(
          site("external_write", file, node, sourceFile, rules, systemForCall(node, rules)),
        );
      } else if (
        name !== null &&
        rules.mark_prefixes.some((p) => name.toLowerCase().startsWith(p))
      ) {
        outcomeSites.push(site("mark_function", file, node, sourceFile, rules));
      } else {
        const system = systemForCall(node, rules);
        if (system !== null) {
          outcomeSites.push(site("external_write", file, node, sourceFile, rules, system));
        }
      }
    } else if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ts.isPropertyAccessExpression(node.left) &&
      node.left.name.text === "status"
    ) {
      outcomeSites.push(site("status_setter", file, node, sourceFile, rules));
    }
    // Python does `stack.extend(n.children)` then pops the LAST — push children forward so
    // pop() takes them last-first, replicating tree-sitter's child order under the same LIFO.
    for (const child of node.getChildren(sourceFile)) stack.push(child);
  }

  return { runBoundaries, outcomeSites, entityIds: entityIdsInFile(sourceFile, rules) };
}
