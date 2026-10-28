# Life cycle of one paid session: create, wait, SSH, run, download, destroy.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Ciclo de vida de uma sessao paga: criar -> aguardar -> SSH -> executar -> baixar dados -> destruir."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from eco import budget, vast
from eco.common import RAW, SSH_KEY, Jsonl, new_run_id, now_utc, write_manifest

SSH_OPTS = ["-i", SSH_KEY, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL", "-o", "ConnectTimeout=20",
            "-o", "ServerAliveInterval=30", "-o", "IdentitiesOnly=yes"]

SELF_DESTRUCT = r"""#!/bin/bash
# rede de seguranca DENTRO da VM (o watchdog externo continua sendo o controle principal)
nohup bash -c 'sleep {sec}; curl -s -X DELETE https://console.vast.ai/api/v0/instances/$CONTAINER_ID/ -H "Authorization: Bearer $CONTAINER_API_KEY"' >/dev/null 2>&1 &
"""


class Lease:
    def __init__(self, tag: str, offer: dict, image: str, disk_gb: int, ttl_min: float):
        self.run_id = new_run_id(tag)
        self.tag, self.offer, self.image, self.disk_gb, self.ttl_min = tag, offer, image, disk_gb, ttl_min
        self.dir = RAW / "leases" / self.run_id
        self.log = Jsonl(self.dir / "lease_events.jsonl")
        self.iid: int | None = None
        self.ssh_host = self.ssh_port = None

    def open(self) -> bool:
        est = self.offer["dph_total"] * (self.ttl_min / 60) + 0.3
        ok, why = budget.can_start(est)
        self.log.write({"event": "budget_check", "ok": ok, "why": why, "est_usd": est})
        if not ok:
            return False
        write_manifest(self.dir, run_id=self.run_id, status="running", offer_snapshot=self.offer, image=self.image,
                       disk_gb=self.disk_gb, ttl_min=self.ttl_min, measurement_kind="measured")
        self.log.write({"event": "create_requested", "offer_id": self.offer["id"], "dph": self.offer["dph_total"]})
        r = vast.create(self.offer["id"], self.image, self.disk_gb, f"eco-{self.tag}",
                        onstart=SELF_DESTRUCT.format(sec=int(self.ttl_min * 60 + 900)))
        self.log.write({"event": "create_response", "resp": {k: ("***" if "key" in k else v) for k, v in (r.get("body") or {}).items()} if isinstance(r.get("body"), dict) else r})
        iid = (r.get("body") or {}).get("new_contract") if isinstance(r.get("body"), dict) else None
        if not iid:
            return False
        self.iid = int(iid)
        budget.register(self.run_id, self.iid, self.ttl_min, "destroy", self.offer["dph_total"], self.tag)
        x = vast.wait_running(self.iid, timeout_s=420)
        if not x:
            self.log.write({"event": "not_running_timeout"})
            return False
        self.ssh_host, self.ssh_port = x["ssh_host"], x["ssh_port"]
        self.log.write({"event": "running", "ssh": f"{self.ssh_host}:{self.ssh_port}", "gpu": x.get("gpu_name")})
        for _ in range(40):
            out = self.sh("echo ready", timeout=30)
            if out and "ready" in out[1]:
                self.log.write({"event": "ssh_ready"})
                return True
            time.sleep(8)
        self.log.write({"event": "ssh_timeout"})
        return False

    def sh(self, cmd: str, timeout: int = 600) -> tuple[int, str] | None:
        try:
            p = subprocess.run(["ssh", *SSH_OPTS, "-p", str(self.ssh_port), f"root@{self.ssh_host}", cmd],
                               capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
            return p.returncode, (p.stdout or "") + (p.stderr or "")
        except subprocess.TimeoutExpired:
            return None

    def put(self, local: str, remote: str) -> bool:
        p = subprocess.run(["scp", *SSH_OPTS, "-P", str(self.ssh_port), "-r", local, f"root@{self.ssh_host}:{remote}"],
                           capture_output=True, text=True, timeout=600)
        return p.returncode == 0

    def get(self, remote: str, local: str) -> bool:
        Path(local).mkdir(parents=True, exist_ok=True)
        p = subprocess.run(["scp", *SSH_OPTS, "-P", str(self.ssh_port), "-r", f"root@{self.ssh_host}:{remote}", local],
                           capture_output=True, text=True, timeout=1800)
        self.log.write({"event": "download", "remote": remote, "ok": p.returncode == 0, "err": (p.stderr or "")[-200:]})
        return p.returncode == 0

    def close(self, reason="done") -> None:
        if self.iid is None:
            return
        self.log.write({"event": "destroy_requested", "reason": reason})
        code = vast.destroy(self.iid)
        for _ in range(12):
            if vast.instance(self.iid) is None:
                break
            time.sleep(5)
        self.log.write({"event": "destroy_confirmed", "http": code, "gone": vast.instance(self.iid) is None})
        budget.unregister(self.run_id, reason)
        write_manifest(self.dir, status="complete" if reason == "done" else "partial", closed_at=now_utc(),
                       spent_usd_after=budget.spent_usd())
