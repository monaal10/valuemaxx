# Security policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting instead:
[**Report a vulnerability**](https://github.com/monaal10/valuemaxx/security/advisories/new).
It is private to the maintainers until a fix ships, and it lets us credit you in the
advisory if you would like that.

If you cannot use GitHub advisories, email **monaalsanghvi1998@gmail.com** instead.
Please say "valuemaxx security" in the subject so it is not missed.

Expect an acknowledgement within a few days. Because valuemaxx is pre-1.0 and
maintained by a small team, please treat that as a best effort rather than an SLA.

## Supported versions

Pre-1.0, only the **latest** minor line receives fixes. There are no long-term support
branches yet.

## What is in scope

The parts of valuemaxx that sit on a request path or hold customer data:

- **The gateway** (`gateway/`) — it proxies live LLM traffic and sees provider keys in
  transit. Anything that could leak a key, alter a forwarded request, or break the
  fail-open guarantee is in scope.
- **The backend** (`apps/`, `packages/`) — tenant isolation above all. Every repository
  method is tenant-scoped by construction; a path that reads or writes across tenants is
  the most serious class of bug this project can have.
- **The published packages** — pip `valuemaxx`, npm `valuemaxx`, and the GHCR backend
  image.

## Design notes that are deliberate, not bugs

Reported before; documented here so you can skip them:

- **The gateway never stores your provider key.** It forwards the `authorization` header
  verbatim and keeps nothing.
- **The gateway fails open.** If our own capture logic throws, the request falls back to
  a plain passthrough. Losing a span is acceptable; losing a customer's LLM call is not.
- **`x-vmx-*` headers are stripped before forwarding.** The provider sees exactly the
  request the host wrote.
- **Self-hosted `VALUEMAXX_INGEST_KEYS` maps a key to a tenant in plain config.** That is
  the self-host model. A hosted control plane with hashed keys is future work, not an
  oversight.
