# valuemaxx gateway

An **observe-only** reverse proxy in front of the LLM providers. Swap your `baseURL`,
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

Every `x-vmx-*` header is stripped before forwarding. Your provider key passes through
untouched and is never stored.

## Why your own id

`x-vmx-run-id: order_9182` groups every call of one unit *and* makes the delayed join
free: when Stripe's webhook arrives days later carrying the same id, the outcome binds
at `exact` tier with no window and no inference. A minted UUID works, but then you must
capture the echoed `x-vmx-run-id` response header and stamp it outward yourself.

## Guarantees

1. **Never breaks your call.** Any internal failure falls back to a plain passthrough.
2. **Never changes your request.** Only `x-vmx-*`, `host`, and `accept-encoding` differ.
3. **Never delays your response.** The body is `tee()`d; capture runs in `waitUntil`.

## Routes

`/openai` · `/anthropic` · `/gemini` · `/openrouter` (whose authoritative `usage.cost`
is recorded as `provider_reconciled` rather than an estimate).

## Deploy

```bash
bunx wrangler deploy --var VALUEMAXX_BACKEND:https://your-backend
```

## Known deployment constraint: Cloudflare error 1042

A Worker on a Cloudflare-owned zone cannot `fetch()` a host that is itself behind
Cloudflare's proxy — the request fails with **error 1042** before it leaves the edge.
`api.anthropic.com` is such a host, so an Anthropic route deployed to a
`*.workers.dev` subdomain returns 1042 while OpenAI/Gemini/OpenRouter work normally.

This is an infrastructure property, not a bug in the gateway: the same code proxies
Anthropic correctly under `wrangler dev` and from any non-Cloudflare host. Options,
in the order worth trying:

1. **Deploy on a custom domain** (a zone you own) rather than `*.workers.dev` — the
   restriction is scoped to Cloudflare-owned zones.
2. **Run the gateway anywhere else** — it is one file of standard `fetch`/streams
   code with no Workers-specific APIs beyond `waitUntil`; a container or any edge
   runtime works.
3. **Route Anthropic through OpenRouter**, which is not Cloudflare-proxied and
   additionally reports authoritative billed cost.

Verify with `/healthz` (always 200) and one real call per provider you plan to use.
