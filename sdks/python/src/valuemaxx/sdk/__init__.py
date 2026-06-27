"""valuemaxx.sdk — the one-line Python SDK that fails open (§5.1, H9).

``import valuemaxx.sdk as valuemaxx; valuemaxx.init(...)`` instruments cost capture
in one call and NEVER crashes the host. A thin façade over ``valuemaxx.capture``:

  * :func:`init` — validate config, self-test SDK versions (warn + degrade on a bad
    one), instrument the injected client's transport (instance-scoped, H1), fail-open;
  * :mod:`track` — ``with track.run(run_id=...)`` binds the ambient run for capture;
  * :mod:`scaffold` — reversible injection of the ``init()`` call site.

Content is OFF by default (§9.1); the ingest key is a SecretStr never logged.
"""

from __future__ import annotations

from valuemaxx.sdk import scaffold, track
from valuemaxx.sdk._bootstrap import InitResult, init
from valuemaxx.sdk.config import EffectiveConfig, InitConfig

__all__ = [
    "EffectiveConfig",
    "InitConfig",
    "InitResult",
    "init",
    "scaffold",
    "track",
]
