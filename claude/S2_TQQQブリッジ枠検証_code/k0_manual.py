"""
K0（マニュアルどおりのS2＝ブレーキ継続）の詳細版マニュアル用の数字を作る。出力：out_k0/
  indicators.csv   投資指標22種（K0・K0換金後・S2旧・QQQ持ちっぱなし・GP持ちっぱなし）
  yearly.csv       年次別リターン   periods.csv  期間別の年率
  monthly_table.csv 月次リターン表  drawdowns.csv 下落の記録
  mc_s2.csv        S2口座だけのMC   mc_household.csv 世帯MC（目標ルール＋DC④、11/6実額起点）
  states.csv       状態の統計       k0_nav.csv 日次NAV（Excel突合用）
"""
import sys, math, json
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import imp_common as C, s2x as X, s2engine as E, hh

OUT = "out_k0"
import os; os.makedirs(OUT, exist_ok=True)
w = C.World("data")
k0 = w.run(dict(keep_brake_on_switch=True))
old = w.run(dict(start_invested=False))
idx = k0["nav"].index
bh = lambda col: (1 + w.assets[col]).cumprod().loc[idx] / (1 + w.assets[col]).cumprod().loc[idx].iloc[0] * 39_700_000
SER = {"K0": k0["nav"], "K0換金後": k0["nav_liq"], "S2旧": old["nav"], "QQQ持ちっぱなし": bh("QQQ1"), "GP持ちっぱなし": bh("GP")}


def ind(nav):
    nav = nav.dropna(); d = nav.pct_change().dropna()
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1
    vol = d.std() * math.sqrt(252)
    down = d[d < -1e-12].std() * math.sqrt(252)
    rm = nav.cummax(); dd = nav / rm - 1
    # 水面下の最長日数（高値を付けた日から次に高値を更新する日まで）
    peak_date = pd.Series(np.where(nav >= rm, nav.index, pd.NaT), index=nav.index).ffill()
    under = (nav.index - pd.DatetimeIndex(peak_date)).days
    m = nav.resample("ME").last(); m0 = pd.concat([pd.Series([nav.iloc[0]], index=[nav.index[0] - pd.Timedelta(days=1)]), m])
    mr = m0.pct_change().dropna()
    y = nav.resample("YE").last(); yr = y.pct_change(); yr.iloc[0] = y.iloc[0] / nav.iloc[0] - 1
    roll5 = (m / m.shift(60)) ** (1 / 5) - 1
    var95 = mr.quantile(0.05)
    last = nav.index[-1]
    r5 = nav[nav.index <= last - pd.DateOffset(years=5)].iloc[-1]
    r1 = nav[nav.index <= last - pd.DateOffset(years=1)].iloc[-1]
    return {"年率（CAGR）": cagr, "累積倍率": nav.iloc[-1] / nav.iloc[0], "年率ボラ": vol, "シャープ（無リスク0）": cagr / vol,
            "ソルティノ": cagr / down, "最大下落": dd.min(), "カルマー": cagr / abs(dd.min()), "水面下の最長日数": float(under.max()),
            "アルサー指数": math.sqrt((dd ** 2).mean()), "最悪の年": yr.min(), "最良の年": yr.max(), "プラスの年の割合": (yr > 0).mean(),
            "月次の勝率": (mr > 0).mean(), "最悪の月": mr.min(), "最良の月": mr.max(), "月次VaR95": var95,
            "月次CVaR95": mr[mr <= var95].mean(), "月次の歪度": mr.skew(), "月次の尖度（超過）": mr.kurt(),
            "5年続けたときの最悪の年率": roll5.min(), "直近5年の年率": (nav.iloc[-1] / r5) ** (1 / 5) - 1, "直近1年": nav.iloc[-1] / r1 - 1}


I = pd.DataFrame({k: ind(v) for k, v in SER.items()})
I.to_csv(f"{OUT}/indicators.csv")

# 年次別
Y = {}
for k, v in SER.items():
    y = v.resample("YE").last(); r = y.pct_change(); r.iloc[0] = y.iloc[0] / v.iloc[0] - 1
    Y[k] = r
Y = pd.DataFrame(Y); Y.index = Y.index.year
Y["USDJPY"] = w.mkt["fx"].loc[idx].resample("YE").last().pct_change().values
Y.loc[2000, "USDJPY"] = w.mkt["fx"].loc[idx].resample("YE").last().iloc[0] / w.mkt["fx"].loc[idx].iloc[0] - 1
st = k0["states"]
Y["年末の状態"] = st["state"].resample("YE").last().values
Y["ブレーキ日数"] = st["braked"].resample("YE").sum().astype(int).values
Y.to_csv(f"{OUT}/yearly.csv")

# 期間別の年率
def cg(v, a, b):
    s = v[(v.index >= a) & (v.index <= b)]
    return (s.iloc[-1] / s.iloc[0]) ** (365.25 / (s.index[-1] - s.index[0]).days) - 1
P = pd.DataFrame({k: {p: cg(v, a, b) for p, (a, b) in {"全期間 2000/4〜2026/10": ("2000-04-01", "2026-10-31"),
                                                         "前半 2000〜2012": ("2000-04-01", "2012-12-31"), "後半 2013〜2026/10": ("2013-01-01", "2026-10-31"),
                                                         "直近10年": ("2016-10-31", "2026-10-31"), "直近5年": ("2021-10-29", "2026-10-31"),
                                                         "ITバブル崩壊 2000/4〜2002/12": ("2000-04-01", "2002-12-31"),
                                                         "リーマン 2007/10〜2009/12": ("2007-10-01", "2009-12-31")}.items()} for k, v in SER.items()})
P.to_csv(f"{OUT}/periods.csv")

# 月次表
m = k0["nav"].resample("ME").last()
m0 = pd.concat([pd.Series([k0["nav"].iloc[0]], index=[pd.Timestamp("2000-03-31")]), m]).pct_change().dropna()
MT = pd.DataFrame({"年": m0.index.year, "月": m0.index.month, "r": m0.values}).pivot(index="年", columns="月", values="r")
MT["年間"] = Y["K0"]
MT.to_csv(f"{OUT}/monthly_table.csv")

# 下落の記録（税引前K0、上位8）
nav = k0["nav"]; liq = k0["nav_liq"]; dd = nav / nav.cummax() - 1
eps = []; inep = False
for t, v in dd.items():
    if v < 0 and not inep: inep, s, mn, mt = True, t, v, t
    elif v < 0 and inep and v < mn: mn, mt = v, t
    elif v >= 0 and inep: eps.append((s, mt, t, mn)); inep = False
if inep: eps.append((s, mt, None, mn))
rows = []
for s, mt, e, mn in sorted(eps, key=lambda x: x[3])[:8]:
    pk = nav[:s].index[-2] if len(nav[:s]) > 1 else s
    rows.append(dict(高値日=pk.date(), 底の日=mt.date(), 回復日=e.date() if e is not None else "未回復", 下落率=mn,
                     底までの日数=(mt - pk).days, 回復までの日数=(e - pk).days if e is not None else None,
                     同じ2日の換金後=liq[mt] / liq[pk] - 1,
                     USDJPYの変化=w.mkt["fx"][mt] / w.mkt["fx"][pk] - 1, QQQドルの変化=w.mkt["qqq"][mt] / w.mkt["qqq"][pk] - 1))
D = pd.DataFrame(rows); D.to_csv(f"{OUT}/drawdowns.csv", index=False)

# S2口座だけのMC（11/6実額起点 3,918.1万）
mr = E.monthly_returns(k0["nav"]); mro = E.monthly_returns(old["nav"])
mc = []
for lbl, r_ in [("K0", mr), ("S2旧", mro)]:
    for yrs in (5, 7):
        for sc in ("基本", "ネガ寄せ", "直近（2013年以降）"):
            if sc == "基本": o = E.monte_carlo(r_, yrs, start=C.W0)
            elif sc == "ネガ寄せ": o = E.monte_carlo(r_, yrs, start=C.W0, weights=E.negative_tilt_weights(r_))
            else: o = E.monte_carlo(r_[r_.index >= "2013-01-01"], yrs, start=C.W0)
            mc.append(dict(案=lbl, 年数=yrs, シナリオ=sc, 一度でも1億=o["p_hit_target"], 中央値=o["median"], 下位10=o["p10"],
                           途中30超下落=o["p_dd_over"], 年率の中央値=o["cagr_median"]))
pd.DataFrame(mc).to_csv(f"{OUT}/mc_s2.csv", index=False)

# 世帯MC（目標ルール＋DC④）
_, T = C.household(w, k0["nav"], k0["states"])
neg = E.negative_tilt_weights(T["S2"])
kw = dict(dc_col=C.D1, cS2=0, cN=50_000, W0=C.W0, D0=C.D0, N0=C.N0)
hm = []
for mo in (12, 36, 60, 84):
    for sc, extra in [("基本", {}), ("ネガ寄せ", dict(weights=neg)), ("直近（2013年以降）", "recent")]:
        if extra == "recent":
            o = hh.hh_mc(T[T.index >= "2013-01-01"], months=mo, **kw)
        else:
            o = hh.hh_mc(T, months=mo, **{**kw, **extra})
        hm.append(dict(年数=mo // 12, シナリオ=sc, 一度でも1億=o["p_hit"], 中央値=o["median"], 下位10=o["p10"], 上位10=o["p90"],
                       途中30超下落=o["p_dd30"], S2中央値=o["med_S2"], DC中央値=o["med_DC"], NISA中央値=o["med_NISA"]))
o = hh.hh_mc(T, start_idx=np.arange(0, len(T) - 60), **kw)
hm.append(dict(年数=5, シナリオ="歴史の5年窓（全部）", 一度でも1億=o["p_hit"], 中央値=o["median"], 下位10=o["p10"], 上位10=o["p90"],
               途中30超下落=o["p_dd30"], S2中央値=o["med_S2"], DC中央値=o["med_DC"], NISA中央値=o["med_NISA"]))
pd.DataFrame(hm).to_csv(f"{OUT}/mc_household.csv", index=False)

# 状態の統計
me = w.judg["base"].dropna(subset=["state"]); me = me[(me.index >= "2000-03-31") & (me.index <= "2026-10-31")]
sw = (me["state"] != me["state"].shift(1)).sum() - 1
bk = st["braked"].astype(int).diff().fillna(0)
S = dict(月数_通常=int((me.state == "NORMAL").sum()), 月数_押し目=int((me.state == "DIP").sum()), 月数_退避=int((me.state == "RETREAT").sum()),
         状態の切替回数=int(sw), ブレーキ発動回数=int((bk > 0).sum()), ブレーキ日数=int(st["braked"].sum()),
         売買回数=int(k0["n_trades"]), 払った税の合計_億円=k0["tax_paid"] / 1e8, 最終の含み益の税_億円=(k0["nav"].iloc[-1] - k0["nav_liq"].iloc[-1]) / 1e8)
json.dump(S, open(f"{OUT}/states.json", "w"), ensure_ascii=False, indent=1, default=float)
pd.DataFrame({"K0": k0["nav"], "K0換金後": k0["nav_liq"]}).to_csv(f"{OUT}/k0_nav.csv")
pd.set_option("display.width", 250)
print(I.round(4).to_string()); print(P.round(4).to_string()); print(D.round(4).to_string()); print(json.dumps(S, ensure_ascii=False, default=float))
print(pd.DataFrame(mc).round(4).to_string()); print(pd.DataFrame(hm).round(4).to_string())
