# Watchdog: destroys instances that no running script owns and enforces the soft stop.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Watchdog independente (processo separado da sessao): encerra lease vencido ou orcamento estourado.
Uso: python -m eco.watchdog   (deixar rodando durante toda a campanha)."""
from __future__ import annotations

import time

from eco import budget, vast
from eco.common import BUDGET_BRL, SOFT_STOP_BRL, Jsonl, now_utc


def tick(log: Jsonl) -> None:
    active = budget.load_active()
    try:
        insts = {x["id"]: x for x in vast.instances()}
    except Exception as e:  # noqa: BLE001
        log.write({"event": "wd_api_error", "err": str(e)[:200]})
        return
    spent = budget.spent_brl()
    over = spent >= BUDGET_BRL * 0.95 or spent >= SOFT_STOP_BRL
    log.write({"event": "wd_tick", "spent_brl": round(spent, 3), "active": list(active), "over_budget": over,
               "instances": [(i, x.get("actual_status"), x.get("dph_total")) for i, x in insts.items()]})
    for lid, l in list(active.items()):
        age_min = (time.time() - l["registered_at"]) / 60
        x = insts.get(l["instance_id"])
        expired = age_min > l["ttl_min"]
        if x is None:
            budget.unregister(lid, "instancia_inexistente")
            continue
        if expired or over:
            reason = "ttl" if expired else "orcamento"
            if l["on_expire"] == "destroy":
                code = vast.destroy(l["instance_id"])
            else:
                code = vast.power(l["instance_id"], "stopped")
            log.write({"event": "wd_kill", "lease_id": lid, "reason": reason, "action": l["on_expire"], "http": code})
            budget.unregister(lid, f"wd_{reason}")
    # instancias eco-* sem lease: orfas -> destruir
    # carencia de 120 s: o lease so e registrado depois do create; destruir antes disso mata sessao saudavel (aconteceu 27/10 08:40, 1,5 s apos criar)
    seen = globals().setdefault("_ORPHAN_SEEN", {})
    live = {l["instance_id"] for l in active.values()}
    for iid, x in insts.items():
        if str(x.get("label") or "").startswith("eco-") and iid not in live:
            first = seen.setdefault(iid, time.time())
            if time.time() - first >= 120:
                code = vast.destroy(iid)
                log.write({"event": "wd_orphan_destroyed", "instance_id": iid, "http": code})
        else:
            seen.pop(iid, None)


if __name__ == "__main__":
    from eco.common import RAW
    log = Jsonl(RAW / "leases" / "watchdog.jsonl")
    budget.baseline_credit()
    log.write({"event": "wd_start", "budget_brl": BUDGET_BRL, "soft_stop_brl": SOFT_STOP_BRL})
    while True:
        try:
            tick(log)
        except Exception as e:  # noqa: BLE001
            log.write({"event": "wd_error", "err": repr(e)[:300]})
        time.sleep(20)
