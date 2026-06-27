"""valuemaxx.capture.otlp — the OTLP wire contract (semconv keys + span ingest).

``semconv`` is the SINGLE source of every OTLP attribute key (gen_ai.* standard +
ai_margin.* valuemaxx extensions). ``otlp_ingest`` decodes a span into a CostEvent
using only those constants, so the Python and TypeScript sides cannot drift (H3).
"""

from __future__ import annotations

from valuemaxx.capture.otlp import semconv
from valuemaxx.capture.otlp.otlp_ingest import span_to_cost_event

__all__ = ["semconv", "span_to_cost_event"]
