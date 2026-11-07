"""
世帯の候補比較（本計算）。候補・判定は cmp_prereg.py（事前登録）。出力：out_cmp/
  series_indicators.csv  S2口座の各持ち方の投資指標（税引後・換金後、2000/4〜2026/10）
  household.csv          候補×シナリオ×5年/7年の物差し（10万本）
  household_20k_same_paths.csv  前回MCと同じ乱数（2万本・60ヶ月）での旧方式と新方式
  decision_main.json     判定1〜3（制約→確率最大→同点なら上振れ）の結果
  paths_<候補>.npz        基本シナリオの経路別の結果（Excel突合・頑健性で使う）
"""
import sys, json, time
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import cmp_common as Q, s2x as X, hh, imp_common as C

OUT = "out_cmp"
import os
os.makedirs(OUT, exist_ok=True)
t0 = time.time()
w = Q.World2("data")
T, S = Q.build_all(w)
T.to_csv(f"{OUT}/month_table.csv")
np.savez_compressed(f"{OUT}/series.npz", names=np.array(list(S)), **{f"r_{k}": v["r"] for k, v in S.items()},
                    **{f"f_{k}": v["f"] for k, v in S.items()}, **{f"wt_{k}": v["wt"] for k, v in S.items()})

# ---------------- 1. S2口座の各持ち方（税引後の投資指標） ----------------
rows = []
for k, sp in Q.SPECS.items():
    z = Q.run_series(w, sp, pretax=False)
    m = X.indicators(z["nav"]); ml = X.indicators(z["res"]["nav_liq"])
    h1 = X.indicators(X.sub(z["nav"], *C.TRAIN)); h2 = X.indicators(X.sub(z["nav"], *C.TEST))
    rows.append(dict(持ち方=k, 年率=m["CAGR"], 換金後年率=ml["CAGR"], ソルティノ=m["Sortino"], 年率ボラ=m["Vol"],
                     最大下落=m["MaxDD"], 最大下落日=m["MaxDD_date"], 換金後最大下落=ml["MaxDD"], 最悪年=m["WorstYear"],
                     最悪5年年率=m["Min5y"], 最悪月=m["WorstMonth"], CVaR95月=m["CVaR95m"], 倍率=m["Multiple"],
                     前半年率=h1["CAGR"], 後半年率=h2["CAGR"], 前半最大下落=h1["MaxDD"], 後半最大下落=h2["MaxDD"],
                     売買回数=z["res"]["n_trades"], 税の合計億=z["res"]["tax_paid"] / 1e8))
si = pd.DataFrame(rows)
si.to_csv(f"{OUT}/series_indicators.csv", index=False)
print(si[["持ち方", "年率", "換金後年率", "ソルティノ", "最大下落", "換金後最大下落", "最悪5年年率", "前半年率", "後半年率"]].round(4).to_string(index=False))

# ---------------- 2. 前回と同じ乱数（2万本・60ヶ月）：旧方式と新方式 ----------------
kw_old = dict(dc_col=Q.D1, cS2=0, cN=50_000, W0=Q.W0, D0=Q.D0, N0=Q.N0)
same = []
for scen in ("基本", "ネガ寄せ", "直近"):
    sk = Q.scen_kw(T, scen)
    Tm = T
    if scen == "直近":
        Tm = T[T.index >= "2013-01-01"]
    for lbl, g, beh in [("A0", False, 2.5), ("A1", True, 2.5), ("A2", True, 2.0)]:
        okw = dict(kw_old, goal=g, behind=beh)
        if scen == "ネガ寄せ":
            okw["weights"] = sk["weights"]
        po = hh.hh_mc(Tm, return_paths=True, months=60, **okw)
        M = Q.draw_months(len(T), 20000, 60, **sk)
        pn = Q.household_mc(T, S, Q.CANDS[lbl], months=60, M=M)
        so, sn = (po["H"] >= 1e8), (pn["H"] >= 1e8)
        same.append(dict(シナリオ=scen, 候補=lbl, 旧方式_1億以上=so.mean(), 新方式_1億以上=sn.mean(),
                         旧方式_元本割れ=(po["H"] < Q.H0).mean(), 新方式_元本割れ=(pn["H"] < Q.H0).mean(),
                         旧方式_途中50超=(po["mindd"] <= -0.5).mean(), 新方式_途中50超=(pn["mindd"] <= -0.5).mean(),
                         旧方式_中央値=np.median(po["H"]), 新方式_中央値=np.median(pn["H"])))
same = pd.DataFrame(same)
same.to_csv(f"{OUT}/household_20k_same_paths.csv", index=False)
print(same.round(4).to_string(index=False))

# ---------------- 3. 本計算：11候補×3シナリオ、84ヶ月（5年は60ヶ月目で切る）、10万本 ----------------
res = []
P5 = {}
for scen in ("基本", "ネガ寄せ", "直近"):
    M = Q.draw_months(len(T), 100_000, 84, seed=42, **Q.scen_kw(T, scen))
    for code in Q.ORDER:
        p = Q.household_mc(T, S, Q.CANDS[code], months=84, M=M)
        for hz in (60, 84):
            s = Q.summarize(p, hz)
            res.append(dict(シナリオ=scen, 期間=hz, 候補=code, 名前=Q.CANDS[code]["name"], **s,
                            濃さ_遅れ=p["lvl"][:, 0].mean(), 濃さ_到達=p["lvl"][:, 3].mean(), 濃さ変更回数=p["nswitch"].mean()))
        if scen == "基本":
            P5[code] = p
            np.savez_compressed(f"{OUT}/paths_{code}.npz", H60=p["H60"], H60L=p["H60L"], mindd60=p["mindd60"],
                                H84=p["H"], H84L=p["HL"], mindd84=p["mindd"], tax=p["tax"])
        if scen == "ネガ寄せ":
            P5["neg_" + code] = (p["H60"] >= 1e8)
    print(scen, "done", round(time.time() - t0, 1), flush=True)
    if scen == "基本":
        np.save(f"{OUT}/M_base_84.npy", M[:2000])      # Excel突合用（先頭2,000本）
hh_df = pd.DataFrame(res)
hh_df.to_csv(f"{OUT}/household.csv", index=False)

# ---------------- 4. 判定1〜3（事前登録の11候補だけ／事後の2候補を含めた13候補） ----------------
b5 = hh_df[(hh_df.シナリオ == "基本") & (hh_df.期間 == 60)].set_index("候補")
ref = b5.loc["A1"]
ok = {c: P5[c]["H60"] >= 1e8 for c in Q.ORDER}


def decide(pool):
    passed = [c for c in pool if b5.loc[c, "元本割れ"] <= ref["元本割れ"] + 1e-12 and b5.loc[c, "途中50超"] <= ref["途中50超"] + 1e-12]
    rank = sorted(passed, key=lambda c: -b5.loc[c, "1億以上"])
    best = rank[0]
    ties = [c for c in rank if c == best or b5.loc[best, "1億以上"] - b5.loc[c, "1億以上"] < 2 * Q.paired_se(ok[best], ok[c])]
    chosen = max(ties, key=lambda c: b5.loc[c, "1億以上の平均"])
    return dict(制約を満たす=passed,
                制約で落ちた={c: dict(元本割れ=float(b5.loc[c, "元本割れ"]), 途中50超=float(b5.loc[c, "途中50超"])) for c in pool if c not in passed},
                確率の順=[(c, float(b5.loc[c, "1億以上"])) for c in rank],
                一位との差の対の標準誤差={c: Q.paired_se(ok[best], ok[c]) for c in rank if c != best},
                同点=ties, 選択_関門前=chosen)


dec = dict(基準A1=dict(元本割れ=float(ref["元本割れ"]), 途中50超=float(ref["途中50超"]), 一億以上=float(ref["1億以上"])),
           事前登録11=decide(Q.ORDER_PRE), 事後を含む13=decide(Q.ORDER))
json.dump(dec, open(f"{OUT}/decision_main.json", "w"), ensure_ascii=False, indent=1, default=float)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
cols = ["候補", "1億以上", "一度でも1億", "中央値", "悪いほう10%", "1億以上の平均", "1.5億以上", "元本割れ", "途中30超", "途中50超", "換金後1億以上", "換金後元本割れ"]
for scen in ("基本", "ネガ寄せ", "直近"):
    for hz in (60, 84):
        d = hh_df[(hh_df.シナリオ == scen) & (hh_df.期間 == hz)]
        print(f"--- {scen} {hz}ヶ月")
        print(d[cols].round(4).to_string(index=False))
print(json.dumps(dec, ensure_ascii=False, indent=1, default=float))
print("total", round(time.time() - t0, 1))
