"""Committed eval fixtures — the N>=50 human-label ground-truth subset (§8.2).

``human_labels_n50.json`` is the non-negotiable human-labeled subset every LLM
judge is validated against (TPR/TNR >= 0.9) before it may be used to grade. It
ships with the package so judge validation is reproducible everywhere.
"""

from __future__ import annotations
