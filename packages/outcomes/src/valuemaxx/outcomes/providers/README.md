# Provider templates

One YAML file per third-party source. Each maps that provider's webhook body onto the
outcome tuple, so a user does not have to reverse-engineer five JSON paths out of
provider documentation before their first number appears.

Shipped today: `stripe`, `hubspot`, `zendesk`.

## Adding one

Drop `<name>.yaml` in this directory. That is the whole step — discovery is a glob, so
there is no registry to edit and no import to add, and `test_providers.py` will hold
your file to the same contract as the others the moment it exists.

```yaml
outcomes:
  - name: deal_closed              # the outcome as the USER would name it
    match:
      webhook: acme                # must equal the filename stem
      event: "deal.won"            # the provider's event type
      when: "data.stage == 'won'"  # optional; AST-allowlisted, never eval'd
    value: "data.amount"           # optional; makes margin-per-outcome possible
    bind:                          # entity keys -> JSON paths (the fallback join)
      deal_id: "data.object_id"
    signal: outcome_confirmed
```

## The three things to get right

**Every rule must be able to reach a run.** Either a `run_id_injection` block (the
provider echoes an id you stamped outbound — strongest, binds at `exact` with no time
window) or a `bind` block (entity keys — honest, but `candidate` tier and outside the
billing-grade denominator). A rule with neither records an outcome that no cost can
ever attach to: a 200, a stored row, and a denominator that quietly excludes it.

**Extract `value` wherever money exists.** It is what turns cost-per-outcome into
margin-per-outcome. A payment template that drops it silently downgrades the headline
number for everyone who uses the file.

**Never declare `outcome_retracted`.** A refund or a reopened ticket is a *later flip*
on an outcome that was genuinely confirmed first — `retract_outcome` owns that
transition. A rule asserting the class up front would be claiming a state change it
never observed, and the loader rejects it.

## Templates are a starting point, not a policy

Nothing here is privileged over a rule a user writes themselves. Every file is parsed
through the same loader and the same AST allowlist as a hand-written
`valuemaxx.outcomes.yaml`, so a template can express nothing a user could not. A host
whose Stripe metadata key is `order_ref` rather than `vmx_run_id` copies the file and
edits one line.
