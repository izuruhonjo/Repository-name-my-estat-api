"""到達を換金後で判定する定義（reach_liq）で、基本シナリオの経路別の結果を保存（Excel突合用）。本計算と同じ乱数。"""
import sys
sys.path.insert(0, ".")
import numpy as np
import cmp_common as Q
w = Q.World2("data"); T, S = Q.build_all(w)
M = Q.draw_months(len(T), 100_000, 84, seed=42)
assert (M[:2000] == np.load("out_cmp/M_base_84.npy")).all()
for c in ("A1", "C3", "D2"):
    p = Q.household_mc(T, S, Q.CANDS[c], months=84, M=M, reach_liq=True)
    np.savez_compressed(f"out_cmp/paths_{c}_RL.npz", H60=p["H60"], H60L=p["H60L"], mindd60=p["mindd60"],
                        H84=p["H"], H84L=p["HL"], mindd84=p["mindd"], tax=p["tax"])
    print(c, (p["H60"] >= 1e8).mean())
