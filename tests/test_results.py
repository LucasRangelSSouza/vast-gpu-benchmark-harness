import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
S = json.loads((ROOT / "results" / "summary.json").read_text())
led = pd.read_csv(ROOT / "data" / "lease_ledger.csv")


def test_ledger_has_no_location_column():
    assert "geo" not in led.columns


def test_ledger_total_matches_summary():
    assert abs(led.est_cost_usd.sum() - S["ledger_usd"]) < 1e-6


def test_reconciled_is_larger_than_hourly_rental():
    assert S["reconciled_total_usd"] > S["hourly_estimate_usd"]


def test_pooling_ceiling_ordering():
    assert S["util_ceiling_1_slot"] < S["util_ceiling_8_slots"] < S["util_ceiling_32_slots"] < 1
