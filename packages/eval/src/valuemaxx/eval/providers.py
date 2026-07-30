"""Production implementations of the eval funnel's injected seams.

The funnel is pure over three protocols — :class:`~valuemaxx.core.context.LlmJudge`,
:class:`~valuemaxx.eval.costgate.ProviderTokenizer` and
:class:`~valuemaxx.eval.types.ReconstructibilityValidator` — and until now only test
stubs implemented them, so ``run_eval_funnel`` could not actually run anywhere. These
are the real ones.

Two deliberate constraints:

* **HTTP is injected, never imported.** Like
  ``valuemaxx.reconciliation.provider_api``, the caller supplies a ``post`` callable.
  The package stays dependency-free and a test drives the whole funnel without a
  network or a monkey-patched client.
* **The candidate's key is passed by the CALLER, per run.** ``run_eval_funnel`` takes
  a ``candidate_secret_ref``, so a user evaluates a model with THEIR key and it is
  never persisted alongside the recommendation.

The judge is capped at the ``directional`` evidence rung by the funnel itself (§8.2) —
an LLM grading an LLM is a signal, not a measurement, and nothing here may promote it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from valuemaxx.core import AtmError
from valuemaxx.eval.types import TaskType, is_reconstructible_task

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOG = logging.getLogger(__name__)

# Keep an eval bounded. A judge asked for a score returns a number, not an essay, and
# a runaway max_tokens on a graded case is real money for no extra signal.
_JUDGE_MAX_TOKENS = 16
_SAMPLE_MAX_TOKENS = 512


class HttpPost(Protocol):
    """The injected HTTP seam: POST JSON, return the decoded body."""

    def post(self, url: str, headers: Mapping[str, str], body: Mapping[str, object]) -> object:
        """POST ``body`` as JSON to ``url``; return the decoded response."""
        ...


class ProviderCallError(AtmError):
    """A candidate-provider call failed or returned an unusable shape."""


def _text_from_anthropic(payload: object) -> str:
    """Pull the assistant text out of an Anthropic messages response."""
    if not isinstance(payload, dict):
        raise ProviderCallError(f"anthropic: expected an object response, got {type(payload)}")
    typed = cast("dict[str, object]", payload)
    content = typed.get("content")
    if not isinstance(content, list):
        raise ProviderCallError("anthropic: response has no content list")
    parts: list[str] = []
    for raw_block in cast("list[object]", content):
        if not isinstance(raw_block, dict):
            continue
        block = cast("dict[str, object]", raw_block)
        if block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def _usage_output_tokens(payload: object) -> int:
    """The provider's own output-token count — never a local re-tokenization."""
    if not isinstance(payload, dict):
        raise ProviderCallError("expected an object response")
    body = cast("dict[str, object]", payload)
    usage = body.get("usage")
    if not isinstance(usage, dict):
        raise ProviderCallError("response carries no usage block")
    typed = cast("dict[str, object]", usage)
    tokens = typed.get("output_tokens", typed.get("completion_tokens"))
    if not isinstance(tokens, int):
        raise ProviderCallError("usage block carries no integer output-token count")
    return tokens


@dataclass(frozen=True, slots=True)
class AnthropicEvalProvider:
    """Anthropic-backed :class:`ProviderTokenizer` + :class:`LlmJudge`.

    ``count_input_tokens`` uses Anthropic's FREE ``/v1/messages/count_tokens``
    endpoint — the provider's own tokenizer, never tiktoken, so an input estimate is
    exact rather than approximately right for the wrong model family.
    """

    http: HttpPost
    api_key: str
    base_url: str = "https://api.anthropic.com"
    version: str = "2023-06-01"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.version,
            "content-type": "application/json",
        }

    def count_input_tokens(self, *, model: str, text: str) -> int:
        """Exact input-token count from the provider's own counter (free endpoint)."""
        payload = self.http.post(
            f"{self.base_url}/v1/messages/count_tokens",
            self._headers(),
            {"model": model, "messages": [{"role": "user", "content": text}]},
        )
        if not isinstance(payload, dict):
            raise ProviderCallError("count_tokens: expected an object response")
        tokens = cast("dict[str, object]", payload).get("input_tokens")
        if not isinstance(tokens, int):
            raise ProviderCallError("count_tokens: response carries no input_tokens")
        return tokens

    def sample_output_tokens(self, *, model: str, text: str) -> int:
        """Run ONE case and report its measured output length (sample-first estimate)."""
        payload = self.http.post(
            f"{self.base_url}/v1/messages",
            self._headers(),
            {
                "model": model,
                "max_tokens": _SAMPLE_MAX_TOKENS,
                "messages": [{"role": "user", "content": text}],
            },
        )
        return _usage_output_tokens(payload)

    def complete(self, *, model: str, prompt: str) -> str:
        """Run one candidate case, returning its text (the graded prediction)."""
        payload = self.http.post(
            f"{self.base_url}/v1/messages",
            self._headers(),
            {
                "model": model,
                "max_tokens": _SAMPLE_MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        return _text_from_anthropic(payload)

    def grade(self, *, prediction: str, reference: str, rubric: str) -> float:
        """Score ``prediction`` against ``reference`` in [0, 1].

        The judge is asked for a bare number and given a tiny token budget: a grader
        that writes prose costs money and adds no signal. An unparseable reply scores
        0.0 rather than raising — a judge that cannot answer is evidence AGAINST
        parity, and failing the whole funnel on one bad grade would be worse.
        """
        instruction = (
            f"{rubric}\n\n"
            "Score how well the CANDIDATE matches the REFERENCE, from 0.0 to 1.0.\n"
            "Reply with only the number.\n\n"
            f"REFERENCE:\n{reference}\n\nCANDIDATE:\n{prediction}\n"
        )
        try:
            payload = self.http.post(
                f"{self.base_url}/v1/messages",
                self._headers(),
                {
                    "model": self.judge_model,
                    "max_tokens": _JUDGE_MAX_TOKENS,
                    "messages": [{"role": "user", "content": instruction}],
                },
            )
            raw = _text_from_anthropic(payload).strip()
            return max(0.0, min(1.0, float(raw.split()[0])))
        except (ProviderCallError, ValueError, IndexError):
            _LOG.warning("valuemaxx eval: judge returned an unusable score; treating as 0.0")
            return 0.0

    @property
    def judge_model(self) -> str:
        """The grading model — small and cheap on purpose; grading is not the product."""
        return "claude-haiku-4-5"


@dataclass(frozen=True, slots=True)
class StructuralReconstructibilityValidator:
    """The default §8.2 gate: delegate to the structural task-type rule.

    A deployment can override per task family by supplying its own implementation;
    this one is the honest default — only classification / extraction / deterministic
    resolution reconstruct their outcome from output alone.
    """

    def is_outcome_reconstructible_from_output(self, task_type: TaskType) -> bool:
        return is_reconstructible_task(task_type)


class UrllibHttpPost:
    """A stdlib :class:`HttpPost` — no new dependency for a handful of eval calls."""

    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self._timeout = timeout_seconds

    def post(self, url: str, headers: Mapping[str, str], body: Mapping[str, object]) -> object:
        """POST JSON via urllib; raises :class:`ProviderCallError` on a transport failure."""
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={**dict(headers)},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:200]
            raise ProviderCallError(f"provider returned {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderCallError(f"provider call failed: {exc}") from exc


__all__ = [
    "AnthropicEvalProvider",
    "HttpPost",
    "ProviderCallError",
    "StructuralReconstructibilityValidator",
    "UrllibHttpPost",
]
