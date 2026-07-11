"""Substantive check for the run_id_wire_parity conformance rule (RUN-ID-CARRY).

Beyond the negative-fixture/foundation-subject checks in ``test_meta.py``, this exercises
the *live* invariant: the T2 baggage consumer and the onboarding proposal read the same
carry key/field as the ``valuemaxx.core.wire`` single source — so the run_id producers
(both SDKs) and the cascade consumer cannot silently drift apart.
"""

from __future__ import annotations

import pytest

from tests.conformance.static import rule_run_id_wire_parity


@pytest.mark.conformance
def test_carry_consumers_read_the_single_source() -> None:
    """No carry consumer's key/field disagrees with valuemaxx.core.wire."""
    offenders = rule_run_id_wire_parity.foundation_consumers_read_the_single_source()
    assert offenders == [], f"carry key/field drift from the single source: {offenders}"
