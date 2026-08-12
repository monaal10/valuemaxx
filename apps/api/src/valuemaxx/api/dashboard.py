"""The local dashboard — `valuemaxx view`'s destination.

A single self-contained HTML page served at ``GET /``. It is the "see your numbers"
surface: without it the backend is an API with no front door, and a user who wires
capture has no way to tell whether it worked short of curling a capability.

DESIGN CONSTRAINTS, each load-bearing:

* **No build step, no CDN, no framework.** The page is one string of HTML+CSS+JS with
  no external fetches. It ships inside the backend image, so it must not need npm at
  build time or network access at run time (a laptop on a plane, an air-gapped CI box,
  and a locked-down corporate network must all render it).
* **It calls the SAME public capability routes a user would.** No private query path,
  no bespoke aggregation endpoint. If the dashboard can show it, an API caller can get
  it — and the dashboard cannot drift from the API by construction.
* **It never invents a number.** Every figure it renders carries the honesty labels the
  capability returned (binding tier, confidence distribution, cost provenance). Where a
  value is absent it says so; a blank is never rendered as a zero, because "no data yet"
  and "zero spend" are different facts and conflating them is exactly the dishonesty the
  tier system exists to prevent.

The four panels answer the four questions a user actually has, in the order they have
them: *is capture even working* (health), *what am I spending* (cost), *what is it
earning* (cost-per-outcome), *what should I change* (eval recommendations).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypedDict

from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from fastapi import FastAPI


class DashboardMetric(TypedDict):
    """A `run_metric` request body the dashboard issues (the public DSL shape)."""

    name: str
    numerator: str
    denominator: str
    filters: dict[str, str]
    group_by: list[str]


# The metric definitions the dashboard runs. These are ordinary `run_metric` bodies —
# the same DSL a user writes — chosen to answer the panel's question with the grammar's
# allowlisted tokens (see valuemaxx.metrics.grammar).
#
# The grammar REJECTS a `total_cost_usd` numerator over any denominator other than
# `verified_outcome_count` — there is no "cost per attempt" metric, deliberately, so a
# cost figure can never be divided by a count that includes advisory or retracted
# outcomes. The spend panels therefore ask for cost-per-outcome grouped by model/agent
# and render the cell's `numerator_value`, which IS the raw spend for that group; the
# ratio column stays honest because it uses the billing-grade denominator.
_SPEND_BY_MODEL: DashboardMetric = {
    "name": "spend_by_model",
    "numerator": "total_cost_usd",
    "denominator": "verified_outcome_count",
    "filters": {},
    "group_by": ["model"],
}
_SPEND_BY_AGENT: DashboardMetric = {
    "name": "spend_by_agent",
    "numerator": "total_cost_usd",
    "denominator": "verified_outcome_count",
    "filters": {},
    "group_by": ["agent_name"],
}
_OUTCOME_VOLUME: DashboardMetric = {
    "name": "outcome_volume",
    "numerator": "outcome_count",
    "denominator": "attempt_count",
    "filters": {},
    "group_by": ["outcome_name"],
}
_COST_PER_OUTCOME: DashboardMetric = {
    "name": "cost_per_outcome",
    "numerator": "total_cost_usd",
    "denominator": "verified_outcome_count",
    "filters": {},
    "group_by": ["outcome_name"],
}

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>valuemaxx</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #ffffff; --fg: #16161a; --muted: #6b6b76; --line: #e4e4e9;
    --card: #fafafa; --accent: #2f6f4f; --warn: #8a6d1f; --bad: #8a3324;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #131316; --fg: #ececf0; --muted: #9a9aa4; --line: #2a2a31;
      --card: #1a1a1f; --accent: #7fc9a0; --warn: #d9b45e; --bad: #e08a76;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font: 15px/1.5 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  header {
    padding: 20px 24px; border-bottom: 1px solid var(--line);
    display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
  }
  h1 { font-size: 17px; margin: 0; letter-spacing: -0.01em; }
  .sub { color: var(--muted); font-size: 13px; }
  main { padding: 24px; display: grid; gap: 20px; max-width: 1100px; }
  section {
    border: 1px solid var(--line); border-radius: 10px;
    background: var(--card); overflow: hidden;
  }
  h2 {
    font-size: 13px; margin: 0; padding: 12px 16px; font-weight: 600;
    border-bottom: 1px solid var(--line); letter-spacing: 0.02em;
  }
  .body { padding: 14px 16px; }
  table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  th, td { text-align: left; padding: 7px 16px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 500; font-size: 12px; }
  tr:last-child td { border-bottom: none; }
  td.num { text-align: right; }
  .empty { color: var(--muted); padding: 14px 16px; font-size: 14px; }
  .tag {
    display: inline-block; padding: 1px 7px; border-radius: 999px;
    font-size: 11px; border: 1px solid var(--line); color: var(--muted);
  }
  .tag.exact { color: var(--accent); border-color: currentColor; }
  .tag.deterministic { color: var(--accent); border-color: currentColor; }
  .tag.candidate { color: var(--warn); border-color: currentColor; }
  .tag.likely { color: var(--warn); border-color: currentColor; }
  .ok { color: var(--accent); }
  .warn { color: var(--warn); }
  .bad { color: var(--bad); }
  code { font: 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; }
  .note { color: var(--muted); font-size: 12.5px; padding: 10px 16px 14px; }
  .picker { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }
  .picker label { display: flex; flex-direction: column; gap: 4px; font-size: 12px;
    color: var(--muted); }
  .picker select, .picker input {
    padding: 6px 8px; border: 1px solid var(--line); border-radius: 6px;
    background: var(--bg); color: var(--fg); font: inherit; font-size: 13px;
  }
  .picker button {
    padding: 7px 14px; border: 1px solid var(--accent); border-radius: 6px;
    background: transparent; color: var(--accent); font: inherit; font-size: 13px;
    cursor: pointer;
  }
  .picker button:disabled { opacity: 0.5; cursor: default; }
</style>
</head>
<body>
<header>
  <h1>valuemaxx</h1>
  <span class="sub">cost per outcome, with confidence &middot; <span id="endpoint"></span></span>
</header>
<main>
  <section><h2>CAPTURE HEALTH</h2><div id="health" class="body">checking&hellip;</div></section>
  <section>
    <h2>COST PER OUTCOME</h2><div id="cpo">loading&hellip;</div>
    <div class="note">
      Billing-grade only: advisory (candidate/likely) and retracted outcomes are
      excluded from the denominator, so this number is never inflated by a guess.
      Each row carries how much to trust it: <b>min tier</b> is the weakest binding
      behind the figure, <b>evidence</b> says whether the link was observed or
      inferred, and <b>split</b> counts runs whose cost is shared with a different
      outcome. A split figure is arithmetic, not a measurement.
    </div>
  </section>
  <section>
    <h2>UNATTRIBUTED SPEND</h2><div id="unattributed" class="body">loading&hellip;</div>
    <div class="note">
      Money spent on runs that joined to no billing-grade outcome. It is shown rather
      than dropped: a number that quietly omits it looks more complete than it is.
      This is usually work that genuinely produced nothing, or an outcome whose join
      key never arrived &mdash; the second kind is fixable with an outcome call or an
      alias.
    </div>
  </section>
  <section>
    <h2>OUTCOMES RECORDED</h2><div id="outcomes">loading&hellip;</div>
    <div class="note">
      What your agents actually produced. An outcome appears here as soon as it is
      recorded; it only reaches the cost-per-outcome denominator once it binds to a run
      at an exact/deterministic tier.
    </div>
  </section>
  <section><h2>SPEND BY MODEL</h2><div id="by-model">loading&hellip;</div></section>
  <section><h2>SPEND BY AGENT</h2><div id="by-agent">loading&hellip;</div></section>
  <section>
    <h2>TRY A CHEAPER MODEL</h2>
    <div class="body">
      <p class="sub" style="margin:0 0 10px">
        Replays your real captured prompts against the candidate and grades the result.
        Say what matters to you and it is graded on that; leave it blank and the run
        asks the generic question, "does the candidate match the incumbent". Your key is
        used for the run and never stored with the recommendation.
      </p>
      <div class="picker">
        <label>incumbent <select id="ev-incumbent"></select></label>
        <label>candidate
          <select id="ev-candidate">
            <option value="claude-haiku-4-5">claude-haiku-4-5</option>
            <option value="claude-sonnet-4-6">claude-sonnet-4-6</option>
            <option value="gpt-5.5">gpt-5.5</option>
          </select>
        </label>
        <label>provider
          <select id="ev-provider">
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
          </select>
        </label>
        <label>your API key <input id="ev-key" type="password" placeholder="sk-..." /></label>
        <label style="flex:1 1 100%">what matters to you (optional)
          <input id="ev-criterion" type="text"
            placeholder="e.g. the bio should be warm and under 20 words" />
        </label>
        <button id="ev-run" type="button">Estimate &amp; run</button>
      </div>
      <div id="ev-status" class="note" style="padding-left:0"></div>
      <div id="ev-savings" class="note" style="padding-left:0"></div>
    </div>
  </section>
  <section>
    <h2>MODEL RECOMMENDATIONS</h2><div id="evals">loading&hellip;</div>
    <div class="note">
      Recommendations are evidence, never an automatic switch. Run
      <code>run_eval_funnel</code> to evaluate a candidate against your real workload.
    </div>
  </section>
</main>
<script>
const KEY = new URLSearchParams(location.search).get("key") || "dev";
document.getElementById("endpoint").textContent = location.origin;

async function call(name, body) {
  try {
    const res = await fetch("/" + name, {
      method: "POST",
      headers: { "content-type": "application/json", "x-api-key": KEY },
      body: JSON.stringify(body ?? {}),
    });
    if (!res.ok) return { __error: "HTTP " + res.status };
    return await res.json();
  } catch (err) {
    return { __error: String(err) };
  }
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// A cell's confidence is the capability's own label — never recomputed here.
function tierTag(tier) {
  if (!tier) return "";
  const t = String(tier).toLowerCase().replace(/^bindingtier\\./, "");
  return '<span class="tag ' + esc(t) + '">' + esc(t) + "</span>";
}

// A numeric cell: the value escaped, or an em-dash when absent. Passing the entity
// through esc() would print a literal "&amp;mdash;" — absent must LOOK absent.
const num = (v) => (v === null || v === undefined ? "&mdash;" : esc(v));

// Was the link between spend and outcome WATCHED, or inferred from a window? An
// inferred join can be right and still must never render as an observed one.
function evidenceTag(evidence) {
  if (!evidence) return "";
  const e = String(evidence).toLowerCase().replace(/^causalevidence\\./, "");
  const cls = e === "observational" ? "warn" : "ok";
  return '<span class="tag ' + cls + '">' + esc(e) + "</span>";
}

// How many of this cell's runs also produced a DIFFERENT outcome, so their cost was
// divided rather than measured. The split keeps columns reconciling against the
// provider invoice; saying nothing would let arithmetic pass as measurement.
function splitTag(count) {
  const n = Number(count || 0);
  if (!n) return '<span class="sub">&mdash;</span>';
  return '<span class="tag warn">' + esc(n) + " shared</span>";
}

// Confirmed outcomes kept OUT of the denominator because their binding is advisory.
// A high count means the real cost per outcome is lower than shown, and the fix is a
// better join key rather than a wider window.
function excludedTag(count) {
  const n = Number(count || 0);
  if (!n) return '<span class="sub">&mdash;</span>';
  return '<span class="tag candidate">' + esc(n) + " advisory</span>";
}

// Spend that reached no billing-grade outcome, stated as a COUNT of unattributed
// attempts rather than a dollar figure.
//
// The honest limit, spelled out because hiding it would be the exact failure this
// panel exists to prevent: every cost measure in the grammar narrows to attributed
// runs, so no capability reports total window spend, and a dollar amount here would
// have to be invented. Attempts and outcomes are both real counts, so the SHARE of
// work that produced nothing bindable is reportable; its cost is not, yet.
function renderUnattributed(el, cpo, volume) {
  if (!cpo || cpo.__error || !volume || volume.__error) {
    el.innerHTML = '<p class="empty">Not available.</p>';
    return;
  }
  const cells = volume.cells || [];
  if (cells.length === 0) {
    el.innerHTML = '<p class="empty">No attempts captured yet.</p>';
    return;
  }
  const attempts = cells.reduce((n, c) => n + Number(c.denominator_value || 0), 0);
  const bound = (cpo.cells || []).reduce((n, c) => n + Number(c.denominator_value || 0), 0);
  const advisory = (cpo.cells || [])
    .reduce((n, c) => n + Number(c.advisory_excluded_count || 0), 0);
  if (!attempts) {
    el.innerHTML = '<p class="empty">No attempts captured yet.</p>';
    return;
  }
  const unbound = Math.max(0, attempts - bound);
  const pct = Math.round((unbound / attempts) * 100);
  el.innerHTML =
    "<p><b>" + esc(unbound) + "</b> of <b>" + esc(attempts) +
    "</b> captured attempts (" + esc(pct) + "%) reached no billing-grade outcome." +
    (advisory
      ? " <b>" + esc(advisory) + "</b> confirmed outcome(s) were excluded as advisory " +
        "&mdash; those have a join that is real but not trusted, which a better join " +
        "key or an alias would promote."
      : "") +
    '</p><p class="sub">Shown as a share of attempts, not dollars: every cost measure ' +
    "narrows to attributed runs, so a dollar figure here would be invented rather " +
    "than measured.</p>";
}

function renderMetric(el, result, valueLabel) {
  if (!result || result.__error) {
    el.innerHTML = '<p class="empty">Not available (' +
      esc(result?.__error ?? "no response") + ")</p>";
    return;
  }
  const cells = result.cells || [];
  if (cells.length === 0) {
    // "No data yet" is a DIFFERENT fact from "zero" — never render 0 here.
    el.innerHTML = '<p class="empty">No data captured yet. Wire the SDK and make an ' +
      "LLM call, then refresh.</p>";
    return;
  }
  const rows = cells.map((c) => {
    const group = (c.group_key || []).map((kv) => kv[1]).join(" / ") || "(all)";
    const value = c.value === null || c.value === undefined ? "&mdash;" : esc(c.value);
    const conf = c.confidence || {};
    return "<tr><td>" + esc(group) + '</td><td class="num">' + value +
      // Escape the VALUE, not the dash: esc("&mdash;") yields a literal "&amp;mdash;".
      '</td><td class="num">' + num(c.numerator_value) +
      '</td><td class="num">' + num(c.denominator_value) +
      "</td><td>" + tierTag(conf.minimum_tier) +
      "</td><td>" + evidenceTag(c.causal_evidence) +
      "</td><td>" + splitTag(c.shared_attribution_count) +
      "</td><td>" + excludedTag(c.advisory_excluded_count) + "</td></tr>";
  }).join("");
  el.innerHTML = "<table><thead><tr><th>group</th><th class='num'>" +
    esc(valueLabel) + "</th><th class='num'>cost (USD)</th><th class='num'>n</th>" +
    "<th>min tier</th><th>evidence</th><th>split</th><th>excluded</th>" +
    "</tr></thead><tbody>" + rows + "</tbody></table>";
}

async function load() {
  const health = await call("capture_healthcheck", {});
  const h = document.getElementById("health");
  if (health.__error) {
    h.innerHTML = '<span class="bad">Backend unreachable</span> &mdash; ' + esc(health.__error);
  } else {
    const alive = health.alive === true;
    const gran = health.capture_granularity ?? "unknown";
    const degraded = String(gran).includes("per_call");
    h.innerHTML =
      (alive
        ? '<span class="ok">Capture alive</span>'
        : '<span class="bad">Capture not alive</span>') +
      ' &middot; granularity <code>' + esc(gran) + "</code>" +
      (degraded
        ? ' <span class="warn">&mdash; degraded to per-call; per-attempt cost is unavailable</span>'
        : "");
  }

  const cpo = await call("run_metric", COST_PER_OUTCOME);
  const volume = await call("run_metric", OUTCOME_VOLUME);
  renderMetric(document.getElementById("cpo"), cpo, "cost / outcome");
  renderUnattributed(document.getElementById("unattributed"), cpo, volume);
  renderMetric(document.getElementById("outcomes"), volume, "outcomes / attempt");
  renderMetric(document.getElementById("by-model"),
    await call("run_metric", SPEND_BY_MODEL), "cost / outcome");
  renderMetric(document.getElementById("by-agent"),
    await call("run_metric", SPEND_BY_AGENT), "cost / outcome");

  // get_recommendation is per-incumbent-model, so ask about the models we actually saw.
  const byModel = await call("run_metric", SPEND_BY_MODEL);
  const models = (byModel.cells || [])
    .map((c) => (c.group_key || []).map((kv) => kv[1]).join(""))
    .filter(Boolean);
  // Populate the incumbent picker from the models actually observed — offering a
  // model the user does not run would be a meaningless comparison.
  const incumbentSel = document.getElementById("ev-incumbent");
  incumbentSel.innerHTML = models.map((m) =>
    '<option value="' + esc(m) + '">' + esc(m) + "</option>").join("") ||
    '<option value="">(no models observed yet)</option>';

  const el = document.getElementById("evals");
  if (models.length === 0) {
    el.innerHTML = '<p class="empty">No models observed yet &mdash; recommendations ' +
      "appear once cost data lands.</p>";
    return;
  }
  const recs = [];
  for (const model of models) {
    const r = await call("get_recommendation", { incumbent_model: model });
    if (!r.__error && r.found === true) recs.push(r);
  }
  if (recs.length === 0) {
    el.innerHTML = '<p class="empty">No recommendations yet. Observed: ' +
      models.map(esc).join(", ") + ".</p>";
    return;
  }
  el.innerHTML = "<table><thead><tr><th>incumbent</th><th>recommended</th>" +
    "<th>grade</th><th>label source</th></tr></thead><tbody>" +
    recs.map((r) =>
      "<tr><td><code>" + esc(r.incumbent_model) + "</code></td><td><code>" +
      esc(r.recommended_model) + "</code></td><td>" + esc(r.grade) +
      "</td><td>" + esc(r.label_source) + "</td></tr>").join("") +
    "</tbody></table>";
}

// --- eval run ---------------------------------------------------------------
// The key is read from the field and sent with THIS request only; it is never
// persisted with the recommendation and never rendered back into the page.
document.getElementById("ev-run").addEventListener("click", async () => {
  const btn = document.getElementById("ev-run");
  const status = document.getElementById("ev-status");
  const incumbent = document.getElementById("ev-incumbent").value;
  const candidate = document.getElementById("ev-candidate").value;
  const provider = document.getElementById("ev-provider").value;
  const key = document.getElementById("ev-key").value;
  const criterion = document.getElementById("ev-criterion").value;

  if (!incumbent) { status.textContent = "No incumbent model observed yet."; return; }
  if (!key) { status.textContent = "Enter your API key for the candidate provider."; return; }

  btn.disabled = true;
  status.textContent = "Submitting eval run…";

  // Show what the switch would cost BEFORE the eval finishes: the estimate is pure
  // arithmetic over traffic already captured, so it needs no provider call and no
  // waiting. It is always ESTIMATED — list price applied to traffic this candidate
  // never actually served — and says so.
  const savings = await call("estimate_switch_cost", {
    incumbent_model: incumbent,
    candidate_model: candidate,
    candidate_provider: provider,
  });
  const savingsEl = document.getElementById("ev-savings");
  if (savings.found) {
    const pct = Number(savings.pct_change);
    const verb = pct < 0 ? "cheaper" : "more expensive";
    savingsEl.innerHTML =
      "Estimated cost on your own captured traffic: <code>$" + esc(savings.incumbent_usd) +
      "</code> \u2192 <code>$" + esc(savings.candidate_usd) + "</code> — " +
      '<span class="' + (pct < 0 ? "ok" : "warn") + '">' + esc(Math.abs(pct).toFixed(1)) +
      "% " + verb + "</span> across " + esc(savings.event_count) +
      " event(s). Estimated (list price), not billed.";
  } else {
    savingsEl.textContent = "No cost estimate: " + (savings.reason ?? "unavailable") + ".";
  }
  const res = await call("run_eval_funnel", {
    incumbent_model: incumbent,
    candidate_model: candidate,
    candidate_provider: provider,
    candidate_secret_ref: key,
    label_source: "outcome_label",
    // Graded against the user's own words when given; otherwise the generic
    // "are these two models at parity" question.
    criterion,
  });
  btn.disabled = false;

  if (res.__error) {
    status.innerHTML = '<span class="bad">Could not start: ' + esc(res.__error) + "</span>";
    return;
  }
  status.innerHTML = res.accepted
    ? '<span class="ok">Eval queued</span> — job <code>' + esc(res.job_id) +
      "</code>. Recommendations appear below when it completes."
    : "Eval was not accepted (check the cost gate).";
});

load();
</script>
</body>
</html>
"""


def mount_dashboard(app: FastAPI) -> None:
    """Serve the dashboard at ``GET /``.

    Injected with the metric bodies so the page and the Python definitions cannot
    drift — there is one source of truth for what the dashboard asks the API.
    """
    page = (
        _PAGE.replace("SPEND_BY_MODEL", json.dumps(_SPEND_BY_MODEL))
        .replace("SPEND_BY_AGENT", json.dumps(_SPEND_BY_AGENT))
        .replace("COST_PER_OUTCOME", json.dumps(_COST_PER_OUTCOME))
        .replace("OUTCOME_VOLUME", json.dumps(_OUTCOME_VOLUME))
    )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> HTMLResponse:  # pyright: ignore[reportUnusedFunction]
        return HTMLResponse(page)


__all__ = ["mount_dashboard"]
