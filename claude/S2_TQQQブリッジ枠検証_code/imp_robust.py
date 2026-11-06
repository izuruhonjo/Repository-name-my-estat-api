"""
妥当性・リスクの検証（技法27・30）。出力：out_imp/
  pbo_dsr.json        全27試行のPBO（CSCV, S=16）と各候補のDSR（試行数27と147の2通り）
  grid48.csv          起点4×コスト3×執行ラグ4で S2 に勝った数
  shift.csv           月末判定を1〜3営業日前にずらした場合の差
  perturb.csv         ブレーキの閾値をゆらした場合の差
  drop_best.csv       最も効いた1年・2年を除いた年率の差（少数の事件への依存度）
"""
import sys, json, itertools, math
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from scipy.stats import skew, kurtosis
import imp_common as C, imp_candidates as K, s2x as X, s2engine as E

w = C.World("data")
allc = {c["code"]: c for c in K.CANDIDATES + K.COMBOS}
FINAL = ["K0", "P1", "C1", "K1", "C2", "C5", "C6", "T1", "L10", "L20"]

# ---------------- 1. PBO・DSR ----------------
M = pd.read_csv("out_imp/monthly_all.csv", index_col=0, parse_dates=True)
trials = [c for c in M.columns if c not in ("S2元", "S2")]
Mx = M[trials].sub(M["S2"], axis=0).dropna()
pbo = E.pbo_cscv(Mx.values, S=16)
sr = Mx.mean() / Mx.std()
res = dict(n_trials=len(trials), PBO=pbo, months=len(Mx), dsr={})
for code in FINAL:
    x = Mx[code].values
    for n in (len(trials), len(trials) + 120):      # 120＝前回のTQQQブリッジ枠検証の試行数
        res["dsr"][f"{code}|N={n}"] = E.deflated_sharpe(float(sr[code]), n_trials=n, sr_var_trials=float(sr.var()),
                                                         T=len(x), skew=float(skew(x)), kurt=float(kurtosis(x, fisher=False)))
    res["dsr"][f"{code}|SR_excess_monthly"] = float(sr[code])
    res["dsr"][f"{code}|nonzero_months"] = int((np.abs(x) > 1e-9).sum())
# 単純なPSR（試行数の補正なし、SR0=0）も参考
for code in FINAL:
    x = Mx[code].values
    s = float(sr[code]); T = len(x)
    from scipy.stats import norm
    z = s * math.sqrt(T - 1) / math.sqrt(1 - skew(x) * s + (kurtosis(x, fisher=False) - 1) / 4 * s * s)
    res["dsr"][f"{code}|PSR(補正なし)"] = float(norm.cdf(z))
json.dump(res, open("out_imp/pbo_dsr.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))

# ---------------- 2. 48通り ----------------
STARTS = ["2000-04-01", "2002-10-01", "2007-10-01", "2013-01-01"]
COSTS = [0.0, 0.0025, 0.005]
LAGS = [1, 2, 3, 5]
rows = []
for s, cst, lag in itertools.product(STARTS, COSTS, LAGS):
    b = w.run({}, None, start=s, slippage=cst, exec_lag=lag)
    mb, mbl = X.indicators(b["nav"]), X.indicators(b["nav_liq"])
    for code in FINAL:
        c = allc[code]
        r = w.run({**c["cfg"], "start": s, "slippage": cst, "exec_lag": lag}, c["policy"], jkey=c["judg"])
        m, ml = X.indicators(r["nav"]), X.indicators(r["nav_liq"])
        rows.append(dict(code=code, start=s, cost=cst, lag=lag, dCAGR=m["CAGR"] - mb["CAGR"], dL_CAGR=ml["CAGR"] - mbl["CAGR"],
                         MaxDD=m["MaxDD"], MaxDD_S2=mb["MaxDD"], L_MaxDD=ml["MaxDD"], L_MaxDD_S2=mbl["MaxDD"],
                         Sortino=m["Sortino"], Sortino_S2=mb["Sortino"]))
g = pd.DataFrame(rows)
g.to_csv("out_imp/grid48.csv", index=False)
summ = g.groupby("code").agg(年率で勝ち=("dCAGR", lambda x: int((x > 0).sum())), 換金後で勝ち=("dL_CAGR", lambda x: int((x > 0).sum())),
                             年率差の平均=("dCAGR", "mean"), 年率差の最小=("dCAGR", "min"),
                             最大下落が悪化=("MaxDD", lambda x: 0)).reindex(FINAL)
summ["最大下落が悪化"] = [int((g[g.code == k].MaxDD < g[g.code == k].MaxDD_S2 - 1e-9).sum()) for k in FINAL]
summ["換金後の最大下落が悪化"] = [int((g[g.code == k].L_MaxDD < g[g.code == k].L_MaxDD_S2 - 1e-9).sum()) for k in FINAL]
summ.to_csv("out_imp/grid48_summary.csv")
print(summ.round(4).to_string())

# ---------------- 3. 月末判定を1〜3営業日前にずらす ----------------
def judge_shift(mkt, k):
    """E.judge_states と同じ規則を、月末のk営業日前の終値で判定（その翌営業日に執行）。"""
    idx = mkt.index
    me = E.month_end_dates(idx)
    pos = idx.get_indexer(me) - k
    dates = idx[pos]
    q = mkt["qqq"].loc[dates]
    sv_px = (1 + E.build_assets(mkt)["SV"]).cumprod()
    svm = sv_px.loc[dates]
    rows, on = [], True
    for i, d in enumerate(dates):
        if i < 12:
            rows.append((d, q.iloc[i], np.nan, np.nan, np.nan, None, np.nan)); continue
        sell = q.iloc[i - 12:i].max() * 0.85; buy = q.iloc[i - 9:i].mean()
        dd = q.iloc[i] / q.iloc[i - 11:i + 1].max() - 1
        if on and q.iloc[i] < sell: on = False
        elif (not on) and q.iloc[i] >= buy: on = True
        st = ("NORMAL" if dd >= -0.10 else "DIP") if on else "RETREAT"
        rows.append((d, q.iloc[i], sell, buy, dd, st, bool(svm.iloc[i] > svm.iloc[i - 12:i].mean())))
    return pd.DataFrame(rows, columns=["date", "qqq", "sell_line", "buy_line", "dd12", "state", "sv_trend"]).set_index("date")

assert judge_shift(w.mkt, 0)["state"].equals(w.judg["base"]["state"])
srows = []
for k in [0, 1, 2, 3]:
    j = judge_shift(w.mkt, k); ctx = X.month_ctx_table(w.mkt, w.assets, j)
    b = X.simulate_x(w.mkt, w.assets, j, X.XCfg(), ctx)
    mb, mbl = X.indicators(b["nav"]), X.indicators(b["nav_liq"])
    srows.append(dict(code="S2", shift=k, CAGR=mb["CAGR"], L_CAGR=mbl["CAGR"], MaxDD=mb["MaxDD"], L_MaxDD=mbl["MaxDD"]))
    for code in FINAL:
        c = allc[code]
        cfg = X.XCfg(**c["cfg"])
        if c["policy"] is not None: cfg.policy = c["policy"]
        r = X.simulate_x(w.mkt, w.assets, j, cfg, ctx)
        m, ml = X.indicators(r["nav"]), X.indicators(r["nav_liq"])
        srows.append(dict(code=code, shift=k, CAGR=m["CAGR"], L_CAGR=ml["CAGR"], MaxDD=m["MaxDD"], L_MaxDD=ml["MaxDD"],
                          dCAGR=m["CAGR"] - mb["CAGR"], dL_CAGR=ml["CAGR"] - mbl["CAGR"]))
sh = pd.DataFrame(srows); sh.to_csv("out_imp/shift.csv", index=False)
print(sh.pivot(index="code", columns="shift", values="dCAGR").reindex(FINAL).round(4).to_string())

# ---------------- 4. 閾値のゆらし ----------------
PERT = {
    "P1": [dict(geo_brake=(g, q)) for g in (0.06, 0.07, 0.08) for q in (-0.04, -0.05, -0.06)],
    "C1": [dict(keep_brake_on_switch=True, geo_brake=(g, q)) for g in (0.06, 0.07, 0.08) for q in (-0.04, -0.05, -0.06)],
    "K1": [dict(brake_frac=f, brake_th=t) for f in (0.75, 1.0) for t in (0.275, 0.30, 0.325)],
    "C2": [dict(brake_frac=1.0, brake_th=t, geo_brake=(g, -0.05)) for t in (0.275, 0.30, 0.325) for g in (0.06, 0.07, 0.08)],
}
b = w.run({}); mb = X.indicators(b["nav"]); mbl = X.indicators(b["nav_liq"])
prow = []
for code, lst in PERT.items():
    for cfg in lst:
        r = w.run(cfg)
        m, ml = X.indicators(r["nav"]), X.indicators(r["nav_liq"])
        prow.append(dict(code=code, cfg=str(cfg), dCAGR=m["CAGR"] - mb["CAGR"], dL_CAGR=ml["CAGR"] - mbl["CAGR"],
                         MaxDD=m["MaxDD"], L_MaxDD=ml["MaxDD"], Sortino=m["Sortino"]))
pt = pd.DataFrame(prow); pt.to_csv("out_imp/perturb.csv", index=False)
print(pt.groupby("code").agg(n=("dCAGR", "size"), 勝ち=("dCAGR", lambda x: int((x > 0).sum())), 平均=("dCAGR", "mean"),
                              最小=("dCAGR", "min"), 最大=("dCAGR", "max")).round(4).to_string())

# ---------------- 5. 最も効いた年を除く ----------------
drow = []
for code in FINAL:
    c = allc[code]; r = w.run(c["cfg"], c["policy"], jkey=c["judg"])
    yc = r["nav_liq"].resample("YE").last(); yb = b["nav_liq"].resample("YE").last()
    yc = pd.concat([pd.Series([r["nav_liq"].iloc[0]], index=[pd.Timestamp("1999-12-31")]), yc]).pct_change().dropna()
    yb = pd.concat([pd.Series([b["nav_liq"].iloc[0]], index=[pd.Timestamp("1999-12-31")]), yb]).pct_change().dropna()
    dlog = np.log1p(yc) - np.log1p(yb)
    n_years = (r["nav"].index[-1] - r["nav"].index[0]).days / 365.25
    order = dlog.sort_values(ascending=False)
    drow.append(dict(code=code, 年率差_換金後=float(np.expm1(dlog.sum() / n_years)),
                     最良年=int(order.index[0].year), 最良年の寄与=float(order.iloc[0]),
                     最良1年を除く=float(np.expm1(order.iloc[1:].sum() / n_years)),
                     最良2年を除く=float(np.expm1(order.iloc[2:].sum() / n_years)),
                     勝ち年数=int((dlog > 1e-6).sum()), 負け年数=int((dlog < -1e-6).sum())))
dr = pd.DataFrame(drow); dr.to_csv("out_imp/drop_best.csv", index=False)
print(dr.round(4).to_string(index=False))
