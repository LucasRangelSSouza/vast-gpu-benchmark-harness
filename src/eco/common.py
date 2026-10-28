# Shared paths and budget constants.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Utilidades comuns: caminhos, JSONL append-only, relogio, manifesto, orcamento."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
ENV_QWEN = Path(os.path.join(os.environ.get("SECRETS_DIR", "secrets"), "qwen-api.env"))
SSH_KEY = str(ROOT / "keys" / "vast_ed25519")

# orcamento (spec §8): R$100 de teto, soft stop R$85, reserva R$15
BUDGET_BRL = float(os.environ.get("BUDGET_BRL", "100"))
SOFT_STOP_BRL = float(os.environ.get("SOFT_STOP_BRL", "85"))
USD_BRL = float(os.environ.get("USD_BRL", "4.9652"))  # awesomeapi 23/10/2026 18:30 UTC (consultado)


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def env_var(name: str, path: Path = ENV_QWEN) -> str:
    m = re.search(rf"^{name}=(.*)$", path.read_text(encoding="utf-8"), re.M)
    if not m:
        raise KeyError(name)
    return m.group(1).strip()


def new_run_id(tag: str) -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{tag}-{uuid.uuid4().hex[:6]}"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Jsonl:
    """Escrita append-only de eventos; um registro por linha, flush imediato."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, rec: dict) -> None:
        rec = {"t_utc": now_utc(), "t_mono_ns": time.monotonic_ns(), **rec}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
            f.flush()


def write_manifest(run_dir: Path, **fields) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    p = run_dir / "manifest.json"
    cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    cur.update(fields)
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return p


def gzip_file(p: Path) -> Path:
    out = p.with_suffix(p.suffix + ".gz")
    with open(p, "rb") as f, gzip.open(out, "wb") as g:
        g.write(f.read())
    return out
