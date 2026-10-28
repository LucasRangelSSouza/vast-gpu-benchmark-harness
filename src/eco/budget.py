# Append-only ledger and budget guard.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Livro-razao e guarda de orcamento (spec §8). Estado em data/raw/leases/*.json (append-only + estado atual)."""
from __future__ import annotations

import json
import time

from eco import vast
from eco.common import BUDGET_BRL, RAW, SOFT_STOP_BRL, USD_BRL, Jsonl, now_utc

LEASES = RAW / "leases"
STATE = LEASES / "active.json"
LEDGER = Jsonl(LEASES / "ledger.jsonl")
BASELINE = LEASES / "baseline.json"


def baseline_credit() -> float:
    LEASES.mkdir(parents=True, exist_ok=True)
    if BASELINE.exists():
        return json.loads(BASELINE.read_text())["credit_usd"]
    c = float(vast.user()["credit"])
    BASELINE.write_text(json.dumps({"credit_usd": c, "t_utc": now_utc(), "usd_brl": USD_BRL}))
    return c


def load_active() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_active(d: dict) -> None:
    LEASES.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, indent=1))


def register(lease_id: str, instance_id: int, ttl_min: float, on_expire: str, dph: float, note: str) -> None:
    a = load_active()
    a[lease_id] = {"instance_id": instance_id, "ttl_min": ttl_min, "on_expire": on_expire, "dph": dph,
                   "registered_at": time.time(), "note": note}
    save_active(a)
    LEDGER.write({"event": "lease_registered", "lease_id": lease_id, "instance_id": instance_id, "ttl_min": ttl_min,
                  "on_expire": on_expire, "dph_usd": dph, "note": note})


def unregister(lease_id: str, reason: str) -> None:
    a = load_active()
    a.pop(lease_id, None)
    save_active(a)
    LEDGER.write({"event": "lease_closed", "lease_id": lease_id, "reason": reason})


def spent_usd() -> float:
    return max(0.0, baseline_credit() - float(vast.user()["credit"]))


def spent_brl() -> float:
    return spent_usd() * USD_BRL


def projected_brl(extra_usd: float = 0.0) -> float:
    return (spent_usd() + extra_usd) * USD_BRL


def can_start(est_usd: float) -> tuple[bool, str]:
    p = projected_brl(est_usd)
    if p >= SOFT_STOP_BRL:
        return False, f"projetado R${p:.2f} >= soft stop R${SOFT_STOP_BRL}"
    return True, f"projetado R${p:.2f} < soft stop R${SOFT_STOP_BRL} (teto R${BUDGET_BRL})"
