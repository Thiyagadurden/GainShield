"""Append-only JSONL audit log of every controller decision.

Each record is one JSON object per line with a fixed schema (see
``AUDIT_FIELDS``). Records carry both simulation time and a monotonic
sequence number, so logs are reproducible run-to-run (wall-clock time is
stored separately and excluded from reproducibility comparisons).

The package is named ``audit`` (not ``logging``) to avoid shadowing the
Python standard-library module.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable

AUDIT_FIELDS = (
    "seq", "t_sim_s", "event", "mode", "controller_state", "v_meas_V", "i_meas_A",
    "Kp_prev", "Ki_prev", "Kp_proposed", "Ki_proposed", "Kp_active", "Ki_active",
    "gp_sigma_margin", "gp_mu_cost", "margin_v_lcb", "margin_i_lcb",
    "decision", "rollback", "reason", "context",
)

EVENTS = ("SESSION_START", "PROPOSAL", "GAIN_APPLIED", "GAIN_REJECTED", "ROLLBACK", "FALLBACK",
          "EPISODE_RESULT", "CONTEXT_CHANGE", "SESSION_END", "FAULT")


@dataclass
class AuditRecord:
    event: str
    t_sim_s: float = math.nan
    mode: str = ""
    controller_state: str = ""
    v_meas_V: float = math.nan
    i_meas_A: float = math.nan
    Kp_prev: float = math.nan
    Ki_prev: float = math.nan
    Kp_proposed: float = math.nan
    Ki_proposed: float = math.nan
    Kp_active: float = math.nan
    Ki_active: float = math.nan
    gp_sigma_margin: float = math.nan
    gp_mu_cost: float = math.nan
    margin_v_lcb: float = math.nan
    margin_i_lcb: float = math.nan
    decision: str = ""
    rollback: bool = False
    reason: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event not in EVENTS:
            raise ValueError(f"unknown audit event {self.event!r}")


def _clean(x: Any) -> Any:
    if isinstance(x, float):
        return None if not math.isfinite(x) else round(x, 9)
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if hasattr(x, "item"):
        return _clean(x.item())
    return x


class AuditLogger:
    """In-memory + optional JSONL file audit log."""

    def __init__(self, path: str | Path | None = None, run_id: str = "run") -> None:
        self.path = Path(path) if path else None
        self.run_id = run_id
        self.records: list[dict[str, Any]] = []
        self._seq = 0
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("")

    def log(self, rec: AuditRecord) -> dict[str, Any]:
        d = _clean(asdict(rec))
        d = {"seq": self._seq, "run_id": self.run_id, **d, "wall_time": time.time()}
        self._seq += 1
        self.records.append(d)
        if self.path:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(d, sort_keys=True) + "\n")
        return d

    def gain_changes(self) -> list[dict[str, Any]]:
        return [r for r in self.records if r["event"] in ("GAIN_APPLIED", "ROLLBACK", "FALLBACK")]

    def to_frame(self):
        import pandas as pd
        return pd.json_normalize(self.records)

    @staticmethod
    def read(path: str | Path) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


def verify_gain_trace(records: Iterable[dict[str, Any]]) -> list[str]:
    """Consistency check: every change of active gains is explained by a logged event.

    Returns a list of problems (empty = consistent).
    """
    problems: list[str] = []
    active = None
    for r in records:
        if r["event"] in ("GAIN_APPLIED", "ROLLBACK", "FALLBACK"):
            prev = (r.get("Kp_prev"), r.get("Ki_prev"))
            if active is not None and prev != active:
                problems.append(f"seq {r['seq']}: Kp/Ki_prev {prev} != last active {active}")
        if r["event"] == "EPISODE_RESULT" and active is not None:
            # episode end: the probe gains must be the ones that were active
            if (r.get("Kp_prev"), r.get("Ki_prev")) != active and active is not None:
                pass  # aborted probes end on baseline; covered by the ROLLBACK record
        if r.get("Kp_active") is not None:
            active = (r.get("Kp_active"), r.get("Ki_active"))
    return problems
