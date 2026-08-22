# Continuous optimization: configuration search over observed traffic

Status: implemented foundation and bounded model/reasoning/token deployment slice.
Written and implemented 22 Aug 2026. Cache-breakpoint and history-depth application
remain represented in the search/frontier contracts but are not mutated by the
gateway until provider-specific semantics can be enforced safely.

## What this is

valuemaxx measures what an outcome costs. This design covers the next step: finding
cheaper ways to produce the same outcome, proving they are safe, and applying them.

The end state is a system a customer configures once by naming the outcome they care
about, which then continuously finds cheaper configurations, proves them on the
customer's own traffic, and applies them within bounds the customer set.

Nothing here is built. It depends on capture, the outcome join, honesty labels and the
non-inferiority test, all of which are shipped.

## Scope: what a proxy can and cannot change

The gateway sits between the host and the provider and sees the full request body. It
can modify anything in that body before forwarding. It cannot change how the host built
the prompt, cannot skip a call the host decided to make, and cannot merge two calls.

That boundary defines the whole design. The searchable space is the request body.
Anything outside it is a suggestion for a human, not a lever for the system.

## Two outputs, deliberately separate

**Search** produces configurations the system can apply itself.

**The linter** produces structural findings a human must act on: a system prompt whose
stable 3,800 tokens sit after the volatile part so nothing caches, a tool block resent
on every turn, retrieved chunks never referenced in any output.

These are different products and mixing them in one list confuses both. The linter is
worth building first: it works at any volume, needs no experiment, and its findings are
usually obviously right.

The linter is allowed to observe prompt STRUCTURE across aggregate traffic. It is not
allowed to rewrite prompt SEMANTICS. "3,800 of 4,200 tokens are byte-identical across
50,000 calls and sit after the volatile part" is a fact. "This instruction is
redundant" is an opinion about something we do not understand, and being wrong there is
expensive and invisible.

## Call sites, not workflows

The unit of optimization is a **call site**: a place in the host's code that calls an
LLM. Every codebase has these whether or not it has an explicit notion of steps or
workflows.

Call sites are derived from traffic, not declared by the host. Calls sharing a `run_id`
are one unit of work; calls with a similar prompt skeleton, model and token profile are
the same call site. `discover_agents` already does this clustering and returns
unconfirmed clusters for a human to confirm, which is the right shape.

Why per call site rather than per application: one application usually contains a
$0.0002 classification and a $0.40 generation. One configuration for both is either
leaving money on the table or breaking the hard one.

Why the split is valid: a change to how one call site is served mostly does not change
what the other call sites receive as input. That is often true and sometimes false -
when call site B consumes call site A's output, making A cheaper can degrade B. The
end-to-end validation against complete units of work is not a formality, it is the
check on this assumption.

**Degradation cases.** An application that reuses one prompt template for everything
clusters into a single call site; the answer there is per-request routing, not
per-site configuration, and that is out of scope for this design. A host that never
groups calls into units can still be optimized per call site but cannot be validated
end to end, and the product must say so.

## What is optimized

Objective:

```
minimise    expected cost per unit of work
subject to  outcome rate  >= baseline - margin
            error rate    <= baseline
            refusal rate  <= baseline
            p95 latency   <= baseline * k
```

Cost is the objective; everything else is a constraint the customer states.

Two deliberate choices here.

**Not a weighted sum.** `cost + λ(1 - outcome_rate)` requires someone to defend a
particular λ, and nobody can. "Do not lose more than one point of conversion" is a
sentence a business person can say yes to.

**The denominator is unit of work, not outcome.** Minimising cost-per-outcome directly
lets the denominator move: a configuration that produces very few but very cheap
outcomes beats one producing many at slightly higher unit cost. Putting the outcome
rate in the constraint prevents winning from the denominator side.

## The search space

Per call site:

| Lever | Space | Notes |
|---|---|---|
| model | 8-30 discrete | most of the money, most of the risk |
| provider | 2-4 per model | cache behaviour differs; must be measured, not assumed |
| reasoning effort | 3-4 discrete | largest lever on reasoning models |
| max_tokens | ~5 useful values | only bites on runaway generations |
| cache breakpoint | ~3 positions | frequently the largest single win, never hand-tuned |
| history depth | ~5 values | riskiest: removes information |

**On provider routing.** Tokenisation is identical for the same model across providers,
so that is not a concern. Cache semantics, TTLs, minimum cacheable prefix lengths and
pricing DO differ between direct Anthropic, Bedrock and Vertex, and since cache
alignment is one of the largest levers, a "free" provider switch can destroy a 70% hit
rate and end up more expensive. Provider belongs in the search space with cache hit
rate measured as a consequence.

**Cost prefilter.** Any candidate not meaningfully cheaper than the incumbent is never
evaluated for quality. Cost is known in advance from the price card and the observed
token mix. This kills most of the space for free and typically leaves tens of
candidates worth replaying.

**Successive halving, not Bayesian optimization.** The space is discrete, small and
cheap to evaluate. Run all candidates on 50 examples, keep the top half, run on 200,
keep the top half, run on 1000. Bayesian optimization earns its keep when evaluations
are expensive and the space is continuous; reserve it for context length and cache
breakpoints if ever needed.

## Explicitly out of scope

- **Prompt rewriting.** Structural suggestions yes, semantic edits no.
- **Request elimination** beyond exact duplicates within a run. Deciding a call was
  unnecessary requires understanding the program, which a proxy does not.
- **Cross-call restructuring.** Batching, merging, dropping steps. Recommendations for
  a human.
- **Per-request routing.** A learned policy choosing configuration per request captures
  more saving but the decision boundary is learned and individual choices cannot be
  explained. Add only once the measurement stack is trustworthy.

## The evidence ladder

Four tiers, each gating the next:

| Tier | Signal | Latency | What it proves |
|---|---|---|---|
| 1 | static analysis | none | provable waste; deploy directly |
| 2 | replay | hours | did not obviously break; says NOTHING about outcomes |
| 3 | live guardrails | hours to a day | error rate, refusal rate, parse failures, latency |
| 4 | outcome non-inferiority | weeks, needs volume | the outcome rate held |

Most decisions are made at tiers 1-3. Tier 4 is the audit that catches "everything
looked fine and conversions quietly dropped" - it is not the trigger, because outcomes
lag by days and cannot catch a fire.

Every recommendation states which tier it rests on, using the existing causal evidence
labels.

### The offline/online gap is the thing to measure

Search runs against replay, but the constraint is about outcomes, and replay cannot
measure outcomes. The gap between them is where optimization systems quietly fail.

The best available offline proxy is **outcome-labelled replay**: we know which
historical runs produced an outcome and which did not, so we replay both populations. A
candidate whose outputs diverge more on the successful population than the unsuccessful
one is suspect. This is only possible because of the outcome join.

Then, crucially: **every time a candidate passes replay and goes to a live test, record
whether the live result agreed.** Over time this yields "replay-passing candidates hold
up 71% of the time on this workload", which is the single most valuable thing the
system produces and which no other vendor can produce.

## Baselines and config identity

### Config is stamped, not declared

Every span carries a config identity computed at the gateway. Baseline is then derived -
"the dominant config at this call site over a recent window" - rather than frozen and
declared. This makes drift visible instead of silent, and lets any historical traffic be
grouped by which config produced it.

Config identity is three hashes, kept separate so a change can be attributed:

```
system_hash  = hash(system message template)
tools_hash   = hash(tool definitions)
params_hash  = hash(model, provider, reasoning, max_tokens, cache config)
```

Conversation content is deliberately excluded; it varies by design and is not
configuration.

### Extracting the system message template

The system message is usually a template with interpolated slots
(`You are helping {customer} on the {plan} plan`), so hashing it raw makes every call
its own config.

Take a rolling sample of ~30 system messages at one call site and find the longest
common subsequence. That is the template; the gaps are slots. This converges fast and
stays stable because system prompts have properties that make it easy: the template is
long and the slots are short, slots appear in consistent positions because they come
from the same format string, and a busy call site produces hundreds of examples per
hour.

Prefer this over Drain-style log clustering. Drain infers structure from text with no
prior knowledge; here the message array is already parsed, roles are already labelled,
and tool definitions are already a separate field. Throwing that structure away to
cluster a flattened blob discards information we were handed.

**Sampling artefact to guard against.** A slot whose value happens to be constant in
the sample gets absorbed into the template - if all 30 calls are for the same customer,
`Acme Corp` looks like template text and the hash changes when a second customer
appears. Mitigations: sample across time and across `run_id`s rather than taking 30
consecutive calls, and judge re-baselining on *how much* of the template changed rather
than whether it changed at all. A genuine prompt edit changes a meaningful chunk; a
sampling artefact changes a few characters.

**When there is no template.** If the common subsequence is very short relative to the
messages, the host is building the system prompt dynamically per request. There is no
template to find. Fall back to hashing structure only (message count, roles, tool
names) and flag that config identity is weak at this call site, rather than producing a
noisy signal.

### Re-baselining

A config change is detected when a different config's share of traffic at a call site
becomes dominant and stays dominant. A share sustained over a window, not a raw count -
a count triggers on a canary that immediately rolls back, and every prompt-touching
deploy would churn the baseline.

On detection:

- the old baseline is marked **superseded and retained**, never deleted
- **experiments in flight against it are invalidated and labelled as such**, rather
  than quietly concluding over mixed traffic
- the new baseline enters **burn-in** until its own outcome rate is measurable - a
  baseline whose rate is unknown cannot anchor a non-inferiority test, because the
  margin is relative to it
- the re-baselining event records its **cause**: "customer changed the prompt" or "we
  applied candidate X". These must not be conflated or the audit trail is lost.

The useful property: baseline drift becomes something the customer can see. "Your
experiment was invalidated because the system prompt changed on Tuesday" is a much
better answer than a result computed over mixed traffic.

## Output: a frontier, not a winner

```
config                       cost/unit   outcome rate   evidence
incumbent                      $0.104        8.2%       measured
haiku on classify only         $0.071        8.1%       live, n=9,400
+ cache realigned              $0.052        7.9%       replay only
haiku everywhere               $0.019        6.1%       FAILS constraint
```

The customer picks the row. The system's job is to be honest about which rows have real
evidence and which are replay-only guesses.

## Application modes

Two modes. No report-only mode: a system that only reports is the observability trap.

**Approve** - the system proposes, a human clicks, the system applies and monitors.
This is where most customers will live, permanently, and that is fine.

**Auto** - the system applies within stated bounds. For customers who have watched it
be right many times.

Rules that hold in both modes:

- opt-in per call site, never global, never inferred
- ramp 1% → 5% → 25% → 100%, with a hold at each step
- **rollback triggers on fast signals only.** The outcome rate lags by days and can
  never be what catches a fire.
- one change at a time per call site; two concurrent experiments on the same traffic
  mean neither concludes
- a one-line kill switch reverting to the host's original config

**This inverts the gateway's founding property.** Today capture fails open: if our code
breaks, the request still goes through. Applying a configuration means our bug becomes
the customer's outage. That is a different reliability commitment and it is the single
biggest risk in this design.

## Build order

1. **Linter.** Cache misalignment and duplicate calls specifically. Works at any
   volume, no experiment, findings usually obviously right.
2. **Model and reasoning search per call site**, gated on replay plus live guardrails.
   Where the money is.
3. **Cache and context levers.** These modify the message array, which is a bigger
   promise than swapping a model name.
4. **Auto mode.** Last, opt-in, ramped.

Config stamping is a prerequisite for 2 and should ship alongside 1.

## Open questions

**Segmentation.** The best configuration for enterprise traffic is probably not the
best for free-tier traffic. Searching one global config leaves money on the table;
searching per segment multiplies sample requirements. Start global, segment only when
the data shows a real interaction.

**Unit of work for the cost denominator.** Cost per run is natural but runs vary in
size. Cost per outcome-eligible run is probably better. This sounds pedantic and it
determines whether numbers are comparable across time.

**Whether customers want Auto at all.** If they want to approve every change, this is a
recommendation engine and the enforcement argument for building it weakens. This is a
five-minute question to a real customer and it should be asked before step 4.

## The honest limit

Tier 4 needs volume - roughly 9,300 units per arm for a one-point margin on an 8%
baseline. Most customers do not have that.

Below that threshold the system degrades to "found cheaper configurations that did not
obviously break anything". That is genuinely useful and it is **not** the same as
proving the outcome held. The product must say which one it did, every time, and the
causal evidence label is the mechanism for saying it.
