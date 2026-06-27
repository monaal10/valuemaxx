"""TS/JS onboarding scan — the ratchet for two bugs caught on a real repo (vibechk):
the scanner was Python-only (found nothing in TypeScript) and walked node_modules
(false outcome sites in vendored code). These tests lock in both fixes.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003  # used at runtime (root / rel, write_text)

from valuemaxx.onboarding.scan import scan_codebase

_VERCEL_AI_SRC = """\
import { generateText, streamText } from "ai";
import { createOpenAI } from "@ai-sdk/openai";

export async function answer(conversationId: string, customerId: string) {
  const openai = createOpenAI({ apiKey: process.env.OPENAI_API_KEY });
  const result = await generateText({ model: openai("gpt-5"), prompt: "hi" });
  return result;
}

export async function stream(applicationId: string) {
  return streamText({ model: openai("gpt-5"), prompt: "go" });
}

export async function markResolved(ticket: Ticket) {
  ticket.status = "resolved";
  await ticket.save();
}
"""

# A vendored file that LOOKS like a hit but lives in node_modules — must be ignored.
_VENDORED = """\
import { generateText } from "ai";
export const x = () => generateText({ prompt: "vendored" });
"""

# A secret-shaped literal the scan must never echo into a snippet.
_WITH_SECRET = """\
const KEY = "sk-ant-api03-REALSECRETVALUE1234567890abcdefghij";
export async function go() {
  return generateText({ apiKey: KEY, prompt: "x" });
}
"""


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_ts_scan_finds_vercel_ai_call_sites(tmp_path: Path) -> None:
    """generateText/streamText/createOpenAI in a .ts src file become run boundaries."""
    _write(tmp_path, "src/agent.ts", _VERCEL_AI_SRC)
    result = scan_codebase(tmp_path)

    boundary_lines = {s.snippet.split("(")[0].strip() for s in result.run_boundaries}
    assert result.run_boundaries, "expected to find LLM run boundaries in the .ts file"
    # the three call kinds are all present somewhere in the boundaries
    joined = " ".join(s.snippet for s in result.run_boundaries)
    assert "generateText" in joined
    assert "streamText" in joined
    assert "createOpenAI" in joined
    assert boundary_lines  # non-empty


def test_ts_scan_finds_outcome_sites_and_entity_ids(tmp_path: Path) -> None:
    """A status setter + an ORM .save() are outcome sites; *Id params are entity ids."""
    _write(tmp_path, "src/agent.ts", _VERCEL_AI_SRC)
    result = scan_codebase(tmp_path)

    kinds = {s.kind for s in result.outcome_sites}
    assert "status_setter" in kinds  # ticket.status = "resolved"
    assert "external_write" in kinds or "mark_function" in kinds  # .save() / markResolved
    assert "conversationId" in result.entity_ids
    assert "customerId" in result.entity_ids
    assert "applicationId" in result.entity_ids


def test_ts_scan_ignores_node_modules(tmp_path: Path) -> None:
    """A generateText call inside node_modules must NOT appear (the vibechk bug)."""
    _write(tmp_path, "src/agent.ts", _VERCEL_AI_SRC)
    _write(tmp_path, "node_modules/ai/dist/index.js", _VENDORED)
    _write(tmp_path, ".worktrees/wip/src/copy.ts", _VENDORED)
    result = scan_codebase(tmp_path)

    all_files = {s.file for s in (result.run_boundaries + result.outcome_sites)}
    assert not any("node_modules" in f for f in all_files), "node_modules must be ignored"
    assert not any(".worktrees" in f for f in all_files), ".worktrees must be ignored"
    assert any(f == "src/agent.ts" for f in all_files), "the real src/ file must still be scanned"


def test_ts_scan_redacts_secrets(tmp_path: Path) -> None:
    """A secret-shaped literal in a scanned .ts file never lands in a snippet."""
    _write(tmp_path, "src/secret.ts", _WITH_SECRET)
    result = scan_codebase(tmp_path)

    for site in result.run_boundaries + result.outcome_sites:
        assert "REALSECRETVALUE" not in site.snippet
        assert "sk-ant-api03-REALSECRETVALUE1234567890abcdefghij" not in site.snippet


def test_mixed_python_and_ts_repo_scans_both(tmp_path: Path) -> None:
    """A repo with both Python and TS source yields sites from both languages."""
    _write(tmp_path, "src/agent.ts", _VERCEL_AI_SRC)
    _write(
        tmp_path,
        "svc/handler.py",
        "def run(customer_id):\n    client.messages.create(model='x')\n",
    )
    result = scan_codebase(tmp_path)
    files = {s.file for s in result.run_boundaries}
    assert any(f.endswith(".ts") for f in files)
    assert any(f.endswith(".py") for f in files)
