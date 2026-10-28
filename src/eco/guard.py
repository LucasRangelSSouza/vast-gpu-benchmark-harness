# Credit guard: destroys campaign instances when the balance falls under a floor.
# Original harness script, copied unmodified apart from this header. Comments inside may be in Portuguese.
"""Guarda de gasto: destroi instancias eco-* se o saldo da Vast cair abaixo de MIN_CREDIT (US$). uso: python -m eco.guard <min_credit> [minutos]"""
import sys
import time

sys.path.insert(0, ".")
from eco import vast  # noqa: E402

lim = float(sys.argv[1])
t_end = time.time() + 60 * float(sys.argv[2] if len(sys.argv) > 2 else 240)
while time.time() < t_end:
    try:
        c = vast.user()["credit"]
        if c < lim:
            for x in vast.instances():
                if str(x.get("label") or "").startswith("eco-"):
                    print(f"GUARDA: saldo {c:.2f} < {lim:.2f}: destruindo {x['id']} ->", vast.destroy(x["id"]), flush=True)
            print("GUARDA ACIONADA", flush=True)
            break
    except Exception as e:  # noqa: BLE001
        print("guarda erro", str(e)[:80], flush=True)
    time.sleep(45)
