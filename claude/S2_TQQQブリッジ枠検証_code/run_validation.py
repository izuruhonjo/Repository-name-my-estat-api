"""
S2 TQQQブリッジ枠 検証ランナー
出力：out/ 以下に CSV / JSON。
"""
import sys, json, math, itertools, time
import numpy as np, pandas as pd
sys.path.insert(0, ".")
import s2engine as E, signals as SG

DATA = sys.argv[1] if len(sys.argv) > 1 else "data"
OUT = "out"
import os; os.makedirs(OUT, exist_ok=True)

mkt = E.load_market(DATA)
assets = E.build_assets(mkt)
judg = E.judge_states(mkt)
ohlc = pd.read_csv(f"{DATA}/QQQ.csv", parse_dates=["date"]).set_index("date")[["high", "low"]].reindex(mkt.index).ffill()
SIG = SG.build_signals(mkt, ohlc)
judg.to_csv(f"{OUT}/judgments.csv")

def run(cfg):
    return E.simulate(mkt, assets, judg, cfg)

def sub(nav, a, b):
    return nav[(nav.index >= a) & (nav.index <= b)]

# ------------------------------------------------------------------
# 1. 正典S2の再現
# ------------------------------------------------------------------
t0 = time.time()
base = run(E.Cfg())
m_base = E.metrics(base["nav"])
print("S2 base:", {k: round(v, 4) if isinstance(v, float) else v for k, v in m_base.items()}, "trades", base["n_trades"], "tax", round(base["tax_paid"] / 1e4), "万円")
base["nav"].to_csv(f"{OUT}/s2_nav.csv")
base["states"].to_csv(f"{OUT}/s2_states.csv")
pd.DataFrame(base["trades"], columns=["date", "asset", "side", "amount", "pnl_after_tax"]).to_csv(f"{OUT}/s2_trades.csv", index=False)

# 持ちっぱなし（税引前、最後に一括課税）
def buyhold(col):
    px = (1 + assets[col]).cumprod()
    px = px[(px.index >= "2000-04-01") & (px.index <= "2026-10-31")]
    nav = px / px.iloc[0] * 39_700_000
    gain = nav.iloc[-1] - nav.iloc[0]
    after = nav.copy(); after.iloc[-1] = nav.iloc[-1] - max(gain, 0) * E.TAX
    return E.metrics(after)
bh = {c: buyhold(c) for c in ["GP", "N1", "QQQ1", "TQQQ", "SV"]}
for c, m in bh.items():
    print(f"B&H {c}:", "CAGR", round(m["CAGR"], 4), "MaxDD", round(m["MaxDD"], 4))

# 年別
nav_y = base["nav"].resample("YE").last()
yr = nav_y.pct_change(); yr.iloc[0] = nav_y.iloc[0] / base["nav"].iloc[0] - 1
qqq_y = (1 + assets["QQQ1"]).cumprod().loc[base["nav"].index].resample("YE").last().pct_change()
pd.DataFrame({"S2": yr, "QQQ_JPY": qqq_y}).to_csv(f"{OUT}/s2_yearly.csv")

# ------------------------------------------------------------------
# 2. 全シグナル × 枠 × 損切り（訓練2000-2012 / 検証2013-2026）
# ------------------------------------------------------------------
TRAIN = ("2000-04-01", "2012-12-31"); TEST = ("2013-01-01", "2026-10-31")
base_tr = E.metrics(sub(base["nav"], *TRAIN)); base_te = E.metrics(sub(base["nav"], *TEST))
rows = []
BUDGETS = [0.10, 0.20, 0.30]; STOPS = [0.25]
for name, sig in SIG.items():
    for bp in BUDGETS:
        for sl in STOPS:
            cfg = E.Cfg(bridge=E.BridgeCfg(enabled=True, asset="TQQQ", budget_pct=bp, stop_loss=sl, signal=sig))
            r = run(cfg)
            m = E.metrics(r["nav"]); mt = E.metrics(sub(r["nav"], *TRAIN)); me = E.metrics(sub(r["nav"], *TEST))
            bl = r["bridge_log"]
            nb = sum(1 for x in bl if x[1] == "BUY"); stops = sum(1 for x in bl if x[1] == "STOP")
            wins = sum(1 for x in bl if x[1] != "BUY" and x[4] is not None and x[4] > 0)
            rows.append(dict(signal=name, budget=bp, stop=sl, CAGR=m["CAGR"], MaxDD=m["MaxDD"], Sharpe=m["Sharpe"],
                             WorstYear=m["WorstYear"], Min5y=m["Min5yCAGR"], Multiple=m["Multiple"],
                             dCAGR=m["CAGR"] - m_base["CAGR"], dMaxDD=m["MaxDD"] - m_base["MaxDD"],
                             train_CAGR=mt["CAGR"], train_dCAGR=mt["CAGR"] - base_tr["CAGR"], train_MaxDD=mt["MaxDD"],
                             test_CAGR=me["CAGR"], test_dCAGR=me["CAGR"] - base_te["CAGR"], test_MaxDD=me["MaxDD"],
                             n_bridge_buys=nb, n_stops=stops, n_wins=wins, n_trades=r["n_trades"]))
res = pd.DataFrame(rows)
res.to_csv(f"{OUT}/all_signals.csv", index=False)
print("signals done", len(res), "runs", round(time.time() - t0), "s")

# 訓練期間で選ぶ：MaxDD(全期間)>=-35%、訓練でdCAGR>0 の中から訓練dCAGR上位
ok = res[(res.train_dCAGR > 0)].sort_values("train_dCAGR", ascending=False)
top = ok.drop_duplicates("signal").head(8)
print(top[["signal", "budget", "train_dCAGR", "test_dCAGR", "dCAGR", "MaxDD"]])
top.to_csv(f"{OUT}/top_by_train.csv", index=False)

# ------------------------------------------------------------------
# 3. 上位候補：ボラ・ブレーキ拡張、別資産、損切り感度
# ------------------------------------------------------------------
ext = []
for _, t in top.head(5).iterrows():
    sig = SIG[t.signal]
    for asset in ["TQQQ", "QLD", "QQQ1", "SOXL", "SMH", "TMF"]:
        for alsovb in [False, True]:
            for sl in [0.15, 0.25, 0.35]:
                cfg = E.Cfg(bridge=E.BridgeCfg(enabled=True, asset=asset, budget_pct=t.budget, stop_loss=sl,
                                               signal=sig, also_volbrake=alsovb))
                r = run(cfg); m = E.metrics(r["nav"]); mt = E.metrics(sub(r["nav"], *TRAIN)); me = E.metrics(sub(r["nav"], *TEST))
                ext.append(dict(signal=t.signal, budget=t.budget, asset=asset, also_volbrake=alsovb, stop=sl,
                                CAGR=m["CAGR"], MaxDD=m["MaxDD"], dCAGR=m["CAGR"] - m_base["CAGR"],
                                train_dCAGR=mt["CAGR"] - base_tr["CAGR"], test_dCAGR=me["CAGR"] - base_te["CAGR"],
                                n_bridge=len([x for x in r["bridge_log"] if x[1] == "BUY"])))
ext = pd.DataFrame(ext); ext.to_csv(f"{OUT}/extensions.csv", index=False)
print("extensions done", round(time.time() - t0), "s")

# ------------------------------------------------------------------
# 4. 48通り（起点4×コスト3×執行ラグ4）：S2 と 上位3候補
# ------------------------------------------------------------------
STARTS = ["2000-04-01", "2002-10-01", "2007-10-01", "2013-01-01"]
COSTS = [0.0, 0.0025, 0.005]
LAGS = [1, 2, 3, 5]
def grid(bridge_cfg_fn):
    out = []
    for s, c, l in itertools.product(STARTS, COSTS, LAGS):
        cfg = E.Cfg(start=s, slippage=c, exec_lag=l, bridge=bridge_cfg_fn())
        m = E.metrics(run(cfg)["nav"])
        out.append(dict(start=s, cost=c, lag=l, CAGR=m["CAGR"], MaxDD=m["MaxDD"]))
    return pd.DataFrame(out)
g48 = {"S2": grid(lambda: E.BridgeCfg())}
finalists = top.head(3)
for _, t in finalists.iterrows():
    g48[t.signal] = grid(lambda t=t: E.BridgeCfg(enabled=True, asset="TQQQ", budget_pct=t.budget, stop_loss=t.stop, signal=SIG[t.signal]))
summary48 = []
for k, g in g48.items():
    if k == "S2":
        continue
    comp = g.merge(g48["S2"], on=["start", "cost", "lag"], suffixes=("", "_S2"))
    comp["beats"] = comp.CAGR > comp.CAGR_S2
    comp.to_csv(f"{OUT}/grid48_{k.replace('/', '_').replace(' ', '')}.csv", index=False)
    summary48.append(dict(signal=k, wins=int(comp.beats.sum()), worst_MaxDD=comp.MaxDD.min(), mean_dCAGR=(comp.CAGR - comp.CAGR_S2).mean()))
summary48 = pd.DataFrame(summary48); summary48.to_csv(f"{OUT}/summary48.csv", index=False)
print(summary48)
print("grid48 done", round(time.time() - t0), "s")

# ------------------------------------------------------------------
# 5. モンテカルロ 20,000本（5年・7年、基本／ネガ寄せ／直近）
# ------------------------------------------------------------------
mc_rows = []
navs = {"S2": base["nav"]}
for _, t in finalists.iterrows():
    navs[t.signal] = run(E.Cfg(bridge=E.BridgeCfg(enabled=True, asset="TQQQ", budget_pct=t.budget, stop_loss=t.stop, signal=SIG[t.signal])))["nav"]
for k, nav in navs.items():
    mr = E.monthly_returns(nav)
    for yrs in (5, 7):
        for scen in ("基本", "ネガ寄せ", "直近"):
            if scen == "基本":
                r = E.monte_carlo(mr, yrs)
            elif scen == "ネガ寄せ":
                r = E.monte_carlo(mr, yrs, weights=E.negative_tilt_weights(mr))
            else:
                r = E.monte_carlo(mr[mr.index >= "2013-01-01"], yrs)
            mc_rows.append(dict(strategy=k, years=yrs, scenario=scen, **r))
mc = pd.DataFrame(mc_rows); mc.to_csv(f"{OUT}/montecarlo.csv", index=False)
print(mc)

# ------------------------------------------------------------------
# 6. PBO（CSCV）と DSR
# ------------------------------------------------------------------
M = []
names = []
for name, sig in SIG.items():
    for bp in BUDGETS:
        cfg = E.Cfg(bridge=E.BridgeCfg(enabled=True, asset="TQQQ", budget_pct=bp, stop_loss=0.25, signal=sig))
        names.append(f"{name}|{bp}")
        M.append(E.monthly_returns(run(cfg)["nav"]).values)
M = np.array(M).T
# S2を引いた超過リターンで評価
base_mr = E.monthly_returns(base["nav"]).values
Mx = M - base_mr[:, None]
pbo = E.pbo_cscv(Mx, S=16)
srs = Mx.mean(axis=0) / Mx.std(axis=0)
from scipy.stats import skew, kurtosis
best = int(np.nanargmax(srs))
dsr = E.deflated_sharpe(float(srs[best]), n_trials=M.shape[1], sr_var_trials=float(np.nanvar(srs)), T=M.shape[0],
                        skew=float(skew(Mx[:, best])), kurt=float(kurtosis(Mx[:, best], fisher=False)))
stats = dict(S2=m_base, buyhold={k: {a: (float(b) if isinstance(b, (float, np.floating)) else b) for a, b in v.items()} for k, v in bh.items()},
             PBO=pbo, DSR_best=dsr, best_trial=names[best], n_trials=int(M.shape[1]), base_trades=base["n_trades"], base_tax=base["tax_paid"],
             train_base=base_tr, test_base=base_te)
json.dump(stats, open(f"{OUT}/stats.json", "w"), ensure_ascii=False, indent=1, default=float)
print("PBO", pbo, "DSR", dsr, names[best])
print("ALL DONE", round(time.time() - t0), "s")
