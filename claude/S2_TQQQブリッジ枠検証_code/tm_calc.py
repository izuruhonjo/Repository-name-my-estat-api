"""
総合マニュアル（S2＝K0、DC＝R0、NISA＝FANG+月5万・ブレーキ半分）の数字を作る（2026-11-07）。出力：out_tm/
  daily.csv        日次の価値（開始日＝1）。S2, S2換金後, DC, NISA, NISAブレーキなし, QQQ, 世帯, 世帯換金後、株フラグ
  indicators.csv   投資指標（全体＝世帯と口座別、QQQと比較）
  yearly.csv       年次リターン
  nisa_real.csv    NISAの実データ期間（2019-11〜）の指標
  rules_eval.csv   売買ルールを1つずつ外した場合（K0エンジン・DCエンジン・NISA）
  mc.csv           世帯MC（正典A0を同じ乱数で再現＋口座別の内訳）、mc_paths.csv（5年・7年末の世帯額）
世帯＝今の構成比（11/6実額：S2 3,918.1万・DC 869.4万・NISA 71.1万）を毎月末に保った場合の仮想の成績。
QQQ＝円建て・配当なし・税なし（詳細版マニュアルの「QQQ持ちっぱなし」と同じ）。
"""
import sys, math, json
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import imp_common as C, s2x as X, s2engine as E, hh, signals as SG
import dc_engine as G
import cmp_common as Q

OUT = "out_tm"
w = C.World("data")
mkt = w.mkt; A = w.A
k0 = w.run(dict(keep_brake_on_switch=True))
idx = k0["nav"].index                      # 米国の営業日 2000-04-03〜2026-10-30
i0 = mkt.index.searchsorted(idx[0]); i1 = mkt.index.searchsorted(idx[-1], side="right")
assert (mkt.index[i0:i1] == idx).all()

# ---------- DC（R0、dc_engine の基準設定） ----------
dw = G.DCWorld()
BASE = dict(delay=4, rate=0.001, dep_model="019")
dcz = G.run_rule(dw, G.RULES["R0"], start="2000-04-01", **BASE)
dc_jp = dcz["nav"]
# 株フラグ（DCが010を持っていた日）を判定から復元：月末判定→翌営業日に売り→4営業日後に買い
cal = dw.cal; ci0 = cal.searchsorted(dc_jp.index[0]); ci1 = cal.searchsorted(dc_jp.index[-1], side="right")
me_k = {dw.me_pos[d]: k for k, d in enumerate(dw.me)}
kprev = max(k for k, d in enumerate(dw.me) if dw.me_pos[d] < ci0)
hold = "010" if G._on(dw.state.iloc[kprev]) else "DEP"
flag = np.zeros(ci1 - ci0); sell_i = buy_i = None; new = None
for i in range(ci0, ci1):
    if sell_i is not None and i == sell_i:
        hold = "CASH"
    if buy_i is not None and i == buy_i:
        hold = new; sell_i = buy_i = None
    flag[i - ci0] = 1.0 if hold == "010" else 0.0
    if i in me_k and sell_i is None and i + 1 < ci1:
        t = "010" if G._on(dw.state.iloc[me_k[i]]) else "DEP"
        cur = hold
        if t != cur:
            new = t; sell_i = i + 1; buy_i = min(i + 1 + 4, ci1 - 1)
dc_flag_jp = pd.Series(flag, index=dc_jp.index)
# 検証：010を持つ日のDCのリターン＝010のリターン（初日を除く）
r_dc = dc_jp.pct_change()
on = (dc_flag_jp == 1) & (dc_flag_jp.shift(1) == 1)
err = (r_dc[on] - dw.R["010"].reindex(dc_jp.index)[on]).abs().max()
assert err < 1e-12, err
# 米国の営業日にそろえる（その日以前の最新の日本の基準価額）
dc = dc_jp.reindex(dc_jp.index.union(idx)).ffill().reindex(idx)
dc_flag = dc_flag_jp.reindex(dc_jp.index.union(idx)).ffill().reindex(idx)
assert dc.notna().all()

# ---------- NISA（FANG+、QQQの20日ボラ30%で半分売り、月末に30%未満なら戻す） ----------
vol_q = SG.realized_vol(mkt["qqq"]).values
me_set = set(E.month_end_dates(mkt.index))


def nisa_sim(th=0.30, frac=0.5, brake=True):
    ra = A["FANG"].values; v = 1.0; nav = np.zeros(i1 - i0); braked = False; on_from = off_from = None
    n_trig = 0; bdays = np.zeros(i1 - i0, bool)
    for i in range(i0, i1):
        k = i - i0
        if on_from is not None and i >= on_from: braked = True; on_from = None
        if off_from is not None and i >= off_from: braked = False; off_from = None
        wgt = (1 - frac) if braked else 1.0
        v *= 1 + wgt * ra[i]; nav[k] = v; bdays[k] = braked
        x = vol_q[i]
        if brake and not braked and on_from is None and not np.isnan(x) and x >= th:
            on_from = i + 1; n_trig += 1
        if mkt.index[i] in me_set and braked and not np.isnan(x) and x < th:
            off_from = i + 1
    return pd.Series(nav, index=idx), n_trig, bdays


nisa, nisa_trig, nisa_bd = nisa_sim()
nisa0, _, _ = nisa_sim(brake=False)

# ---------- QQQ・S2 ----------
qqq = (1 + w.assets["QQQ1"]).cumprod().loc[idx]
s2 = k0["nav"]; s2l = k0["nav_liq"]
s2_flag = k0["states"]["state"].isin(["NORMAL", "DIP"]).astype(float).reindex(idx)

# ---------- 世帯（今の構成比を毎月末に保つ） ----------
WTS = np.array([C.W0, C.D0, C.N0]) / (C.W0 + C.D0 + C.N0)


def household(parts):
    P = np.column_stack([p.values / p.values[0] for p in parts])
    mon = idx.to_period("M")
    H = np.zeros(len(idx)); anchorP = P[0].copy(); anchorH = 1.0
    for t in range(len(idx)):
        if t > 0 and mon[t] != mon[t - 1]:
            anchorP = P[t - 1].copy(); anchorH = H[t - 1]
        H[t] = anchorH * float((WTS * P[t] / anchorP).sum())
    return pd.Series(H, index=idx)


hh_nav = household([s2, dc, nisa]); hh_liq = household([s2l, dc, nisa])
hh_flag = WTS[0] * s2_flag + WTS[1] * dc_flag + WTS[2] * 1.0
norm = lambda s: s / s.iloc[0]
D = pd.DataFrame({"世帯": norm(hh_nav), "世帯換金後": norm(hh_liq), "S2": norm(s2), "S2換金後": norm(s2l), "DC": norm(dc),
                  "NISA": norm(nisa), "NISAブレーキなし": norm(nisa0), "QQQ": norm(qqq),
                  "株_S2": s2_flag, "株_DC": dc_flag, "株_NISA": 1.0, "株_世帯": hh_flag, "株_QQQ": 1.0}, index=idx)
D.index.name = "date"
D.to_csv(f"{OUT}/daily.csv")
SERIES = ["世帯", "世帯換金後", "S2", "S2換金後", "DC", "NISA", "QQQ"]
FLAG = {"世帯": "株_世帯", "世帯換金後": "株_世帯", "S2": "株_S2", "S2換金後": "株_S2", "DC": "株_DC", "NISA": "株_NISA", "QQQ": "株_QQQ"}


# ---------- 指標 ----------
def monthly(nav):
    m = nav.resample("ME").last()
    m0 = pd.concat([pd.Series([nav.iloc[0]], index=[nav.index[0] - pd.Timedelta(days=1)]), m])
    return m, m0.pct_change().dropna()


def ind(nav, bench, flag):
    nav = nav.dropna(); d = nav.pct_change().dropna()
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1
    vol = d.std() * math.sqrt(252)
    down = d[d < -1e-12].std() * math.sqrt(252)
    rm = nav.cummax(); dd = nav / rm - 1
    tb = dd.idxmin(); peak_v = rm.loc[tb]
    tp = nav[(nav.index <= tb) & (nav >= peak_v)].index[-1]          # 最大下落の高値の日
    after = nav[(nav.index > tb) & (nav >= peak_v)]
    trec = after.index[0] if len(after) else None
    rec_m = (trec - tp).days / (365.25 / 12) if trec is not None else float("nan")
    m, mr = monthly(nav); _, br = monthly(bench.loc[nav.index])
    y = nav.resample("YE").last(); yr = y.pct_change(); yr.iloc[0] = y.iloc[0] / nav.iloc[0] - 1
    roll5 = (m / m.shift(60)) ** (1 / 5) - 1
    var95 = mr.quantile(0.05)
    up, dn = br > 0, br < 0
    ex = mr - br
    return {"年率": cagr, "累積倍率": nav.iloc[-1] / nav.iloc[0], "ボラ（年率）": vol, "最大下落": dd.min(),
            "最大下落の日": str(tb.date()), "最大下落の高値の日": str(tp.date()),
            "回復までの月数": rec_m, "回復した日": str(trec.date()) if trec is not None else "未回復",
            "シャープ": cagr / vol, "ソルティノ": cagr / down, "カルマー": cagr / abs(dd.min()),
            "最悪年": yr.min(), "最良年": yr.max(), "最悪月": mr.min(), "CVaR95（月次）": mr[mr <= var95].mean(),
            "最悪5年年率": roll5.min(), "勝ち月の割合": (mr > 0).mean(),
            "ベータ（対QQQ）": np.cov(mr, br, ddof=1)[0, 1] / br.var(ddof=1), "相関（対QQQ）": np.corrcoef(mr, br)[0, 1],
            "上昇の追随率": mr[up].mean() / br[up].mean(), "下落の追随率": mr[dn].mean() / br[dn].mean(),
            "情報比（対QQQ）": ex.mean() * 12 / (ex.std(ddof=1) * math.sqrt(12)),
            "株を持っていた割合": float(flag.loc[nav.index].mean())}


I = pd.DataFrame({s: ind(D[s], D["QQQ"], D[FLAG[s]]) for s in SERIES})
I.to_csv(f"{OUT}/indicators.csv")
Yr = {}
for s in SERIES + ["NISAブレーキなし"]:
    y = D[s].resample("YE").last(); r = y.pct_change(); r.iloc[0] = y.iloc[0] / D[s].iloc[0] - 1; Yr[s] = r
Yr = pd.DataFrame(Yr); Yr.index = Yr.index.year; Yr.index.name = "年"
Yr.to_csv(f"{OUT}/yearly.csv")
# NISAの実データ期間（FNGS 2019-11〜）
r0 = A.index[A["FANG_real"]].min()
sub = D[D.index >= r0]
NR = pd.DataFrame({s: ind(sub[s], sub["QQQ"], sub["株_NISA"]) for s in ["NISA", "NISAブレーキなし", "QQQ"]})
NR.to_csv(f"{OUT}/nisa_real.csv")

# ---------- 売買ルールを1つずつ外した場合 ----------
def k0m(res):
    m = X.indicators(res["nav"]); ml = X.indicators(res["nav_liq"])
    h1 = X.indicators(X.sub(res["nav"], "2000-04-01", "2012-12-31")); h2 = X.indicators(X.sub(res["nav"], "2013-01-01", "2026-10-31"))
    return dict(年率=m["CAGR"], 換金後年率=ml["CAGR"], 最大下落=m["MaxDD"], 換金後最大下落=ml["MaxDD"], ソルティノ=m["Sortino"],
                最悪5年年率=m["Min5y"], 前半年率=h1["CAGR"], 後半年率=h2["CAGR"], 売買回数=res["n_trades"])


def pol_nodip(c):
    p = X.default_policy(c)
    return {"GP": 1.0} if c["state"] == "DIP" else p


def pol_cash(c):
    return {"CASH": 1.0} if c["state"] == "RETREAT" else X.default_policy(c)


rows = []; RD = {}
K0C = dict(keep_brake_on_switch=True)
asof = lambda nv: nv.reindex(nv.index.union(idx)).ffill().reindex(idx)
for key, lbl, res in [
    ("S2_K0", "S2：K0（今のルール全部）", k0),
    ("S2_ブレーキなし", "S2：ボラ・ブレーキを外す", w.run({**K0C, "vol_brake": False})),
    ("S2_押し目なし", "S2：押し目を外す（○はいつもゴールドプラス）", w.run(K0C, pol_nodip)),
    ("S2_待避なし", "S2：守り待避を外す（×はいつも円現金）", w.run(K0C, pol_cash)),
    ("S2_全部売り", "S2：ブレーキで全部売る（今は半分）", w.run({**K0C, "brake_frac": 1.0})),
    ("S2_毎日戻す", "S2：ブレーキを月末でなく毎日戻す（25%未満の翌日）", w.run({**K0C, "restore": "daily"})),
    ("S2_2日遅れ", "S2：売買を判定の2営業日後にする（1日遅れ）", w.run({**K0C, "exec_lag": 2})),
]:
    rows.append(dict(key=key, 案=lbl, **k0m(res)))
    RD[key] = res["nav"] / res["nav"].iloc[0]; RD[key + "_換金後"] = res["nav_liq"] / res["nav_liq"].iloc[0]
gp = (1 + w.assets["GP"]).cumprod().loc[idx]
mg = X.indicators(gp)
rows.append(dict(key="S2_GP持ちっぱなし", 案="S2：○×をやめてゴールドプラスを持ちっぱなし（税なし）", 年率=mg["CAGR"], 換金後年率=np.nan,
                 最大下落=mg["MaxDD"], 換金後最大下落=np.nan, ソルティノ=mg["Sortino"], 最悪5年年率=mg["Min5y"],
                 前半年率=X.indicators(X.sub(gp, "2000-04-01", "2012-12-31"))["CAGR"], 後半年率=X.indicators(X.sub(gp, "2013-01-01", "2026-10-31"))["CAGR"], 売買回数=0))


def dcm(nav):
    m = X.indicators(nav)
    return dict(年率=m["CAGR"], 換金後年率=m["CAGR"], 最大下落=m["MaxDD"], 換金後最大下落=m["MaxDD"], ソルティノ=m["Sortino"], 最悪5年年率=m["Min5y"],
                前半年率=X.indicators(X.sub(nav, "2000-04-01", "2012-12-31"))["CAGR"], 後半年率=X.indicators(X.sub(nav, "2013-01-01", "2026-10-31"))["CAGR"])


for key, lbl, kw, rule in [("DC_R0", "DC：R0（今のルール）", {}, "R0"), ("DC_持ちっぱなし", "DC：○×をやめて野村外国株式インデックスファンドを持ちっぱなし", {}, "R1"),
                           ("DC_遅延1", "DC：売りから買いまで1営業日（参考）", {"delay": 1}, "R0"),
                           ("DC_遅延8", "DC：売りから買いまで8営業日（遅れた場合）", {"delay": 8}, "R0")]:
    z = G.run_rule(dw, G.RULES[rule], start="2000-04-01", **{**BASE, **kw})
    zn = asof(z["nav"]); RD[key] = zn / zn.iloc[0]
    rows.append(dict(key=key, 案=lbl, 売買回数=z["nsw"], **dcm(zn)))
for key, lbl, s in [("NISA_今", "NISA：FANG+、ブレーキで半分（今のルール）", nisa), ("NISA_ブレーキなし", "NISA：ブレーキなし（持ちっぱなし）", nisa0),
                    ("NISA_全部", "NISA：ブレーキで全部売る", nisa_sim(frac=1.0)[0])]:
    rows.append(dict(key=key, 案=lbl, 売買回数=np.nan, **dcm(s))); RD[key] = s / s.iloc[0]
RD["S2_GP持ちっぱなし"] = gp / gp.iloc[0]
pd.DataFrame(RD).to_csv(f"{OUT}/rules_daily.csv")
RE = pd.DataFrame(rows)
RE.to_csv(f"{OUT}/rules_eval.csv", index=False)

# ---------- 世帯MC（正典A0を同じ乱数で再現） ----------
w2 = Q.World2("data")
T, S = Q.build_all(w2, specs={"K0_予定どおり": Q.SPECS["K0_予定どおり"]})
M = Q.draw_months(len(T), 100_000, 84, seed=42)
p = Q.household_mc(T, S, Q.CANDS["A0"], months=84, M=M)
ref = pd.read_csv("out_cmp/household.csv")
ref = ref[(ref["候補"] == "A0") & (ref["シナリオ"] == "基本")].set_index("期間")
mc = []
for hz in (60, 84):
    s = Q.summarize(p, hz)
    assert abs(s["1億以上"] - ref.loc[hz, "1億以上"]) < 1e-12 and abs(s["中央値"] - ref.loc[hz, "中央値"]) < 1e-3, (hz, s["1億以上"], ref.loc[hz, "1億以上"])
    mc.append(dict(期間=hz, **s))
mc = pd.DataFrame(mc)
# 口座別（7年末）：p["W"],p["D"],p["N"] は 84ヶ月末。5年末の口座別は record で取り直す
p2 = Q.household_mc(T, S, Q.CANDS["A0"], months=60, M=M[:, :60])
assert np.allclose(p2["H"], p["H60"])
acc = []
for hz, W_, D_, N_, H_ in [(60, p2["W"], p2["D"], p2["N"], p2["H"]), (84, p["W"], p["D"], p["N"], p["H"])]:
    for name, v in [("S2", W_), ("DC", D_), ("NISA", N_), ("世帯", H_)]:
        acc.append(dict(期間=hz, 口座=name, 中央値=np.median(v), 悪いほう10=np.percentile(v, 10), 良いほう10=np.percentile(v, 90), 平均=v.mean()))
pd.DataFrame(acc).to_csv(f"{OUT}/mc_accounts.csv", index=False)
mc.to_csv(f"{OUT}/mc.csv", index=False)
pd.DataFrame({"H60": p["H60"], "H84": p["H"], "hit60": p["hit60"].astype(int), "hit84": p["hit"].astype(int),
              "dd60": p["mindd60"], "dd84": p["mindd"],
              "W60": p2["W"], "D60": p2["D"], "N60": p2["N"], "W84": p["W"], "D84": p["D"], "N84": p["N"]}).to_csv(f"{OUT}/mc_paths.csv", index=False)
meta = dict(weights=dict(S2=WTS[0], DC=WTS[1], NISA=WTS[2]), W0=C.W0, D0=C.D0, N0=C.N0, nisa_trig=nisa_trig,
            nisa_brake_days=float(nisa_bd.mean()), nisa_real_start=str(r0.date()), start=str(idx[0].date()), end=str(idx[-1].date()),
            dc_flag_check=float(err), k0_n_brake=k0["n_brake"], k0_n_trades=k0["n_trades"])
json.dump(meta, open(f"{OUT}/meta.json", "w"), ensure_ascii=False, indent=1, default=float)
print(I.to_string()); print(RE.round(4).to_string()); print(mc.T.to_string()); print(meta)
