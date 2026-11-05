"""世帯3口座の動的ポートフォリオ検証ランナー（DC・NISAのスイッチング＋S2のG5）"""
import sys, json
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import s2engine as E, hh

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
DATA = sys.argv[1] if len(sys.argv) > 1 else "data"
OUT = "out_hh"; import os; os.makedirs(OUT, exist_ok=True)

mkt = hh.load_all(DATA)
A = hh.asset_returns(mkt)
assets = E.build_assets(mkt); judg = E.judge_states(mkt)
s2 = E.simulate(mkt, assets, judg, E.Cfg())
TR, TE = ("2000-04-01", "2012-12-31"), ("2013-01-01", "2026-10-31")
sub = lambda s, a, b: s[(s.index >= a) & (s.index <= b)]

# ---------------- 1. DC戦略の単体成績（拠出なし・時間加重） ----------------
rows = []; dc_navs = {}
for name, rule in hh.DC_RULES.items():
    nav, hold, nsw = hh.run_dc(mkt, A, judg, rule)
    dc_navs[name] = nav
    m, mt, me = E.metrics(nav), E.metrics(sub(nav, *TR)), E.metrics(sub(nav, *TE))
    share = hold.value_counts(normalize=True)
    rows.append(dict(戦略=name, 年率=m["CAGR"], 最大下落=m["MaxDD"], 最悪年=m["WorstYear"], 最悪5年=m["Min5yCAGR"],
                     前半年率=mt["CAGR"], 後半年率=me["CAGR"], 前半DD=mt["MaxDD"], 後半DD=me["MaxDD"],
                     切替回数=nsw, 年あたり切替=nsw / m["Years"], 株の割合=1 - share.get("PRIN", 0) - share.get("CASH", 0) - share.get("FBOND", 0)))
dc_tab = pd.DataFrame(rows); dc_tab.to_csv(f"{OUT}/dc_strategies.csv", index=False)
print("== DC戦略（2000-04〜2026-10、円建て・配当込み・拠出なし） =="); print(dc_tab.round(4).to_string())

# ---------------- 2. NISA（FANG+）の単体成績 ----------------
nis = {"N0 FANG+持ちっぱなし": hh.run_hold(A, "FANG")}
nv, hold, nsw = hh.run_nisa_switch(mkt, A, judg); nis["N1 ○×でFANG+⇔国内債券（枠制約は無視）"] = nv
nis["参考 NASDAQ100持ちっぱなし"] = hh.run_hold(A, "NDX1")
rows = []
for k, nv in nis.items():
    m, me = E.metrics(nv), E.metrics(sub(nv, *TE))
    rows.append(dict(戦略=k, 年率=m["CAGR"], 最大下落=m["MaxDD"], 後半年率=me["CAGR"], 後半DD=me["MaxDD"]))
real0 = A.index[A["FANG_real"]].min() if A["FANG_real"].any() else None
for k in (["FANG", "NDX1"] if real0 is not None else []):
    nv = hh.run_hold(A, k, start=str(real0.date()))
    m = E.metrics(nv); rows.append(dict(戦略=f"FNGS実データ期間 {real0.date()}〜 {k}", 年率=m["CAGR"], 最大下落=m["MaxDD"], 後半年率=np.nan, 後半DD=np.nan))
if real0 is not None:
    nv, hold, nsw = hh.run_nisa_switch(mkt, A, judg, start=str(real0.date()))
    m = E.metrics(nv); rows.append(dict(戦略=f"FNGS実データ期間 ○×切替", 年率=m["CAGR"], 最大下落=m["MaxDD"], 後半年率=np.nan, 後半DD=np.nan))
nisa_tab = pd.DataFrame(rows); nisa_tab.to_csv(f"{OUT}/nisa_strategies.csv", index=False)
print("\n== NISA（FANG+） =="); print(nisa_tab.round(4).to_string())

# ---------------- 3. 世帯モンテカルロ ----------------
dc_navs["N1"] = nis["N1 ○×でFANG+⇔国内債券（枠制約は無視）"]
T = hh.build_month_table(s2["nav"], s2["states"], dc_navs, A, rate_daily=mkt["rate"])
T.to_csv(f"{OUT}/month_table.csv")
neg = E.negative_tilt_weights(T["S2"])
D1 = "D1 DC④（○先進国株／×元本確保）"
cases = []
def case(label, **kw):
    base = dict(dc_col=D1)
    base.update(kw)
    r = hh.hh_mc(T, **base)
    rn = hh.hh_mc(T, weights=neg, **base)
    roll_starts = np.arange(0, len(T) - 60)
    rr = hh.hh_mc(T, start_idx=roll_starts, **base)
    cases.append(dict(案=label, 一度でも1億=r["p_hit"], 中央値=r["median"], 下位10=r["p10"], 途中DD30=r["p_dd30"], 途中DD50=r["p_dd50"],
                      ネガ寄せ1億=rn["p_hit"], 歴史5年窓1億=rr["p_hit"], 歴史窓DD30=rr["p_dd30"],
                      S2中央=r["med_S2"], DC中央=r["med_DC"], NISA中央=r["med_NISA"], NISA移管中央=r["med_moved"]))
case("現状（S2＋DC④＋NISA持ちっぱなし）", goal=False, cS2=0)
case("G5-A（目標ルール＋S2積立5万）", cS2=50_000)
for name in hh.DC_RULES:
    if name == D1:
        continue
    case(f"G5-A × DC={name}", cS2=50_000, dc_col=name)
case("G5-A × DC④・×中も掛金は先進国株", cS2=50_000, dc_contrib_to="A_DEV")
case("G5-A × NISAも○×切替（枠制約無視）", cS2=50_000, nisa_col="N1")
for f in [0.10, 0.25, 0.50, 1.00]:
    case(f"G5-A × ×の月にS2の{int(f*100)}%を空き枠までNISAへ", cS2=50_000, nisa_from_s2_in_retreat=f)
case("G5-A × ×の月だけS2積立5万をNISAへ", cS2=50_000, s2c_to_nisa_in_ret=True)
case("G5-A × 毎年1月にS2から空き枠を埋める", cS2=50_000, nisa_jan_fill=1.0)
case("G5-A × S2積立5万をNISA積立に回す（NISA月10万）", cS2=0, cN=100_000)
mc = pd.DataFrame(cases); mc.to_csv(f"{OUT}/household_mc.csv", index=False)
print("\n== 世帯モンテカルロ（20,000本、5年、世帯合計1億） ==")
show = mc.copy()
for c in ["中央値", "下位10", "S2中央", "DC中央", "NISA中央", "NISA移管中央"]:
    show[c] = (show[c] / 1e4).round(0)
print(show.round(3).to_string())
