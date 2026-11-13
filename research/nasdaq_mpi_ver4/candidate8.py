"""候補8: 「米ドルMMF・6%超→2倍」(A) と「全額すぐ1倍・3倍固定」(B) を、最大下落率を入れた基準と10年窓で比べる（100万円一括）

設計・判定は candidate8_prereg.md に計算前に固定（コミット 32fdcb3）。エンジン(mpi.py)は変更しない。
  窓: 10年窓（毎年1月開始）。感応度として5年窓、100万円+月3万円。NDX 2022/9- は全期間を参考で。
  指標: F=税引後最終資産 / R=税引後年率 / D=最大下落率（円建て日次評価額）/ MAR=R÷|D|
  窓の値=締め日21通りの中央値、セットの値=窓の値の中央値
"""
import sys
sys.path.insert(0, ".")
from multiprocessing import Pool
from simple_rules import *

RULE = "12か月線"
RATE = dict(rate_thr=0.06, rate_mode="monthly")
VARS = {"A": dict(exit_mode="mmf", **RATE), "B": dict(exit_mode="one"),
        "A'": dict(exit_mode="mmf"), "B'": dict(exit_mode="one", **RATE), "基準": dict(exit_mode="drip")}
VARN = {"A": "A 米ドルMMF・6%超→2倍", "B": "B 全額すぐ1倍・3倍固定", "A'": "A' 米ドルMMF・3倍固定",
        "B'": "B' 全額すぐ1倍・6%超→2倍", "基準": "基準 現金→毎月1%ずつ1倍", "K0": "K0 MPI・月末締め",
        "3倍保有": "3倍保有", "1倍保有": "1倍保有"}
REFS = ["K0", "3倍保有", "1倍保有"]
WSETS = [s for s in SETS2 if not s[0].startswith("NDX 2022")]      # 10年窓が取れる6セット
REFSET = [s for s in SETS2 if s[0].startswith("NDX 2022")][0]       # 参考（全期間）
G = {}


def years_of(a, b):
    return ((pd.Period(b, "M") - pd.Period(a, "M")).n + 1) / 12.0


def work(t):
    wtype, lab, kind, ix, a, b, mon, var, k = t
    C = replace(base_cfg(*G["cost"][ix]), start=a, end=b, initial=INITIAL, monthly=mon)
    if var in BENCH:
        r, _, _ = run(G["D"][ix], DUMMY, replace(C, strategy=BENCH[var]))
    elif var == "K0":
        r, _ = run_rule(G["D"][ix], G["K0"][ix], C)
    else:
        r, _ = run_rule(G["D"][ix], G["SIG"][(ix, k)], replace(C, **VARS[var]))
    return dict(wtype=wtype, set=lab, kind=kind, idx=ix, var=var, k=k, start=a, end=b, years=years_of(a, b),
                final=r["final_after_liq"], contrib=r["contrib"], irr=r["irr"], mdd_usd=r["mdd_twr"], mdd_yen=r["mdd_value"],
                trades=r["n_trades"], n_switch=r["n_switch"], share2=r["share_2x"])


def tasks():
    T = []
    for lab, kind, ix, st, en in WSETS:
        for a, b in windows(st, en, 10):
            for v in VARS:
                T += [("10年窓", lab, kind, ix, a, b, 0.0, v, k) for k in KS]
            T += [("10年窓", lab, kind, ix, a, b, 0.0, v, 0) for v in REFS]
            for v in ("A", "B"):
                T += [("10年窓+月3万", lab, kind, ix, a, b, 30000.0, v, k) for k in KS]
        for a, b in windows(st, en, 5):
            for v in ("A", "B"):
                T += [("5年窓", lab, kind, ix, a, b, 0.0, v, k) for k in KS]
    lab, kind, ix, st, en = REFSET
    for v in VARS:
        T += [("参考全期間", lab, kind, ix, st, en, 0.0, v, k) for k in KS]
    T += [("参考全期間", lab, kind, ix, st, en, 0.0, v, 0) for v in REFS]
    return T


def main():
    D = datasets()
    cost = {}
    for k, (e3, e2) in CAL.items():
        cost[k] = (calibrate_cost(D[k], e3, 3)[0], calibrate_cost(D[k], e2, 2)[0])
    cost["IXIC"] = cost["NDX"]
    G.update(D=D, cost=cost,
             SIG={(ix, k): rule_signals(shifted_bars(D[ix], k), RULE) for ix in D for k in KS},
             K0={ix: rule_signals(shifted_bars(D[ix], 0), "MPI(ver4.0)") for ix in D})
    T = tasks()
    print("runs", len(T), flush=True)
    rows = []
    with Pool(4) as p:                       # fork: G を子プロセスと共有
        for i, r in enumerate(p.imap(work, T, chunksize=40)):
            rows.append(r)
            if i % 3000 == 0:
                print(i, flush=True)
    R = pd.DataFrame(rows)
    R["R"] = np.where(R.wtype == "10年窓+月3万", R.irr, (R.final / INITIAL) ** (1 / R.years) - 1)
    R["D"] = np.where(R.wtype == "10年窓+月3万", R.mdd_usd, R.mdd_yen)   # 積立ありは入金で評価額が歪むので時間加重(ドル建て)
    R["MAR"] = R.R / R.D.abs()
    pd.to_pickle(dict(res=R, cost=cost, sig0={ix: G["SIG"][(ix, 0)] for ix in D}), "data/candidate8.pkl")
    for k in D:
        D[k].to_pickle(f"data/daily_{k}.pkl")
    print("done", len(R))


if __name__ == "__main__":
    main()
