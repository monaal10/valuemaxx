# valuemaxx gateway

An **observe-only by default** reverse proxy in front of the LLM providers. Swap your `baseURL`,
set a couple of headers, and cost-per-outcome appears — no SDK, no run boundaries, no
flush, no code in your request path.

```python
client = OpenAI(
    base_url="https://<your-gateway>/openai/v1",
    default_headers={"x-vmx-key": "vmx_live_...", "x-vmx-run-id": order_id},
)
client.chat.completions.create(..., extra_headers={"x-vmx-outcome": "order_fulfilled"})
```

## Headers

| Header | Meaning | Default |
|---|---|---|
| `x-vmx-key` | your valuemaxx key (selects the tenant) | capture off |
| `x-vmx-run-id` | the unit of work — **use your own durable id** | one minted per request, echoed back |
| `baggage` | W3C alias for the run id (`valuemaxx.run_id=...`) | — |
| `x-vmx-agent` | agent name for grouping | — |
| `x-vmx-entity-<name>` | durable business ids (`x-vmx-entity-order-id: 9182`) | — |
| `x-vmx-outcome` | business outcome this call completes (fires on 2xx only) | — |
| `x-vmx-call-site` | confirmed call site eligible for a bounded deployment | — |
| `x-vmx-bypass` | `1`/`true`/`on` immediately serves the host's original config | — |

Every `x-vmx-*` header is stripped before forwarding. Your provider key passes through
untouched and is never stored.

## Why your own id

`x-vmx-run-id: order_9182` groups every call of one unit *and* makes the delayed join
free: when Stripe's webhook arrives days later carrying the same id, the outcome binds
at `exact` tier with no window and no inference. A minted UUID works, but then you must
capture the echoed `x-vmx-run-id` response header and stamp it outward yourself.

## Guarantees

1. **Never breaks your call.** Any internal failure falls back to a plain passthrough.
2. **Never changes your request by default.** A change requires an enabled,
   source-matched deployment for an explicit call site; bypass always restores the original.
3. **Never delays your response.** The body is `tee()`d; capture runs in `waitUntil`.

## Routes

`/openai` · `/anthropic` · `/gemini` · `/openrouter` (whose authoritative `usage.cost`
is recorded as `provider_reconciled` rather than an estimate).

## Deploy

```bash
bunx wrangler deploy --var VALUEMAXX_BACKEND:https://your-backend
```
