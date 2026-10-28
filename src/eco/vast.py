# Thin client for the Vast.ai REST API (offers, create, destroy, balance).
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Cliente minimo da API da Vast.ai (ofertas, criar, status, destruir). Nunca imprime a chave."""
from __future__ import annotations

import json
import time

import httpx

from eco.common import RAW, Jsonl, env_var

BASE = "https://console.vast.ai/api"


def _h() -> dict:
    return {"Authorization": "Bearer " + env_var("VAST_API_KEY")}


def user() -> dict:
    return _get(f"{BASE}/v0/users/current/").json()


def search(min_vram_gb=0, max_dph=None, gpu_names=None, extra=None, limit=500) -> list[dict]:
    q = {"verified": {"eq": True}, "external": {"eq": False}, "rentable": {"eq": True}, "type": "on-demand",
         "limit": limit, "order": [["dph_total", "asc"]], "num_gpus": {"eq": 1},
         "gpu_ram": {"gte": int(min_vram_gb * 1000)}}
    if max_dph:
        q["dph_total"] = {"lte": max_dph}
    if gpu_names:
        q["gpu_name"] = {"in": gpu_names}
    q.update(extra or {})
    r = httpx.post(f"{BASE}/v0/bundles/", headers=_h(), json=q, timeout=60)
    r.raise_for_status()
    offers = r.json().get("offers", [])
    Jsonl(RAW / "provider_offers" / "offers.jsonl").write({"event": "search", "query": q, "n": len(offers), "offers": offers})
    return offers


def create(offer_id: int, image: str, disk_gb: int, label: str, onstart: str = "", env: dict | None = None,
           runtype: str = "ssh_direct") -> dict:
    body = {"client_id": "me", "image": image, "disk": disk_gb, "label": label, "runtype": runtype,
            "onstart": onstart, "env": env or {}}
    r = httpx.put(f"{BASE}/v0/asks/{offer_id}/", headers=_h(), json=body, timeout=60)
    return {"status": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text}


def _get(url, **kw):
    for i in range(12):
        r = httpx.get(url, headers=_h(), timeout=30, **kw)
        if r.status_code in (429, 500, 502, 503):
            time.sleep(min(60, 4 * (i + 1)) + (hash(url) % 5))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def instances() -> list[dict]:
    return _get(f"{BASE}/v1/instances/").json().get("instances", [])


def instance(iid: int) -> dict | None:
    for x in instances():
        if x["id"] == iid:
            return x
    return None


def destroy(iid: int) -> int:
    return httpx.delete(f"{BASE}/v0/instances/{iid}/", headers=_h(), timeout=60).status_code


def power(iid: int, state: str) -> int:
    return httpx.put(f"{BASE}/v0/instances/{iid}/", headers=_h(), json={"state": state}, timeout=60).status_code


def wait_running(iid: int, timeout_s=900, poll=15) -> dict | None:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        x = instance(iid)
        if x and x.get("actual_status") == "running" and x.get("ssh_host"):
            return x
        time.sleep(poll)
    return None
