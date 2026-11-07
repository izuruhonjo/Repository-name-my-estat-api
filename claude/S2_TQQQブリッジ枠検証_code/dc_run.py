"""
DC規則の一斉比較 ③ の本計算（事前登録 dc_prereg.py ＋追記1〜5）。出力 out_dc/
  dc_alone.csv        DC単体（全期間＝つないだもの、実データの期間）
  household.csv       世帯MC（全12規則が揃う月、10万本、基本／ネガ寄せ／直近、5年・7年、確実性等価）
  household_full.csv  参考：全期間（2000-05〜、R2を除く11規則＋従来のDC④）
  dep_sens.csv        預金の感応度（従来の0.1%一定、018）
  grid64.csv / grid64_summary.csv   起点4×遅延4×利率4
  cscv_household.csv / pbo_dsr.json
  monthly_base.csv    各規則の月次リターン（基準）
  decision.json       判定
"""
import sys, json, math, time, itertools
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from scipy.stats import skew, kurtosis
import cmp_common as Q, s2engine as E, s2x as X, hh
import dc_engine as G

OUT = "out_dc"
import os; os.makedirs(OUT, exist_ok=True)
t0 = time.time()
ORDER = G.ORDER
GAM = (1, 3, 5)
BASE = dict(delay=4, rate=0.001, dep_model="019")

# ---------------- 準備 ----------------
w = Q.World2("data")
T, S = Q.build_all(w, specs={"K0_予定どおり": Q.SPECS["K0_予定どおり"]})
TT = len(T)
dw = G.DCWorld()
CAND = Q.CANDS["A0"]


def series(start="2000-04-01", **kw):
    out, info = {}, {}
    for k in ORDER:
        z = G.run_rule(dw, G.RULES[k], start=start, **{**BASE, **kw})
        out[k] = G.monthly(z["nav"]).reindex(T.index)
        info[k] = z
    return pd.DataFrame(out), info


MB, INFO = series()
MB.to_csv(f"{OUT}/monthly_base.csv")
lo = int(np.argmax(MB.notna().all(axis=1).values))
assert MB.iloc[lo:].notna().all().all()
print("共通の月", T.index[lo].date(), "〜", T.index[-1].date(), TT - lo, "ヶ月", flush=True)


def T_with(col):
    T2 = T.copy()
    T2[Q.D1] = np.nan_to_num(col.values if hasattr(col, "values") else col)
    return T2


def ce(H, g):
    x = H / 1e4
    if g == 1:
        return float(np.exp(np.mean(np.log(x)))) * 1e4
    return float(np.mean(x ** (1 - g)) ** (1 / (1 - g))) * 1e4


def ce_diff_se(Ha, Hb, g):
    """CE(a)−CE(b) の対の標準誤差（デルタ法）。"""
    xa, xb = Ha / 1e4, Hb / 1e4
    if g == 1:
        ua, ub = np.log(xa), np.log(xb)
        ga, gb = math.exp(ua.mean()), math.exp(ub.mean())        # 1/u'(CE)=CE
    else:
        ua, ub = xa ** (1 - g) / (1 - g), xb ** (1 - g) / (1 - g)
        ca, cb = (ua.mean() * (1 - g)) ** (1 / (1 - g)), (ub.mean() * (1 - g)) ** (1 / (1 - g))
        ga, gb = ca ** g, cb ** g                                 # 1/u'(CE)=CE^γ
    cov = np.cov(np.vstack([ua, ub]))
    v = ga ** 2 * cov[0, 0] + gb ** 2 * cov[1, 1] - 2 * ga * gb * cov[0, 1]
    return math.sqrt(max(v, 0) / len(ua)) * 1e4


def mc(col, M, months=84, **kw):
    return Q.household_mc(T_with(col), S, CAND, months=months, M=M, **kw)


def starts_kw(scen, lo_):
    if scen == "基本":
        return dict(starts=np.arange(lo_, TT - 11))
    if scen == "ネガ寄せ":
        return dict(starts=np.arange(lo_, TT - 11), weights=E.negative_tilt_weights(T["S2"]))
    if scen == "直近":
        l2 = int(np.searchsorted(T.index, pd.Timestamp("2013-01-01")))
        return dict(starts=np.arange(max(lo_, l2), TT - 11))
    raise ValueError(scen)


# =============================================================
# 1. DC単体
# =============================================================
rows = []
for k in ORDER:
    nav = INFO[k]["nav"]
    m_all = X.indicators(nav)
    rs = G.real_start(dw, k)
    m_real = X.indicators(nav[nav.index >= rs])
    rows.append({"規則": k, "内容": G.RULES[k][0], "開始": str(nav.index[0].date()), "年率": m_all["CAGR"], "最大下落": m_all["MaxDD"],
                 "ソルティノ": m_all["Sortino"], "最悪5年年率": m_all["Min5y"], "スイッチ回数": INFO[k]["nsw"], "預金の比率": INFO[k]["dep_share"],
                 "実データの開始": str(pd.Timestamp(rs).date()), "実_年率": m_real["CAGR"], "実_最大下落": m_real["MaxDD"],
                 "実_ソルティノ": m_real["Sortino"], "実_最悪5年年率": m_real["Min5y"]})
alone = pd.DataFrame(rows)
alone.to_csv(f"{OUT}/dc_alone.csv", index=False, encoding="utf-8-sig")
print(alone.round(4).to_string(index=False), flush=True)

# =============================================================
# 2. 世帯MC（本計算）
# =============================================================
KEYS5 = ["1億以上", "中央値", "悪いほう10%", "元本割れ", "途中30超", "途中50超", "換金後1億以上", "1億以上の平均"]
hrows = []
PATHS = {}
for scen in ("基本", "ネガ寄せ", "直近"):
    M = Q.draw_months(TT, 100_000, 84, seed=42, **starts_kw(scen, lo))
    P = {k: mc(MB[k], M) for k in ORDER}
    if scen == "基本":
        PATHS = P
    ref = P["R0"]
    for k in ORDER:
        p = P[k]
        s5, s7 = Q.summarize(p, 60), Q.summarize(p, 84)
        r = {"シナリオ": scen, "規則": k}
        r.update({f"5年_{x}": s5[x] for x in KEYS5})
        r.update({f"7年_{x}": s7[x] for x in ("1億以上", "中央値", "悪いほう10%", "元本割れ", "途中50超")})
        r["5年_平均"] = float(p["H60"].mean())
        ok, ok0 = p["H60"] >= Q.G, ref["H60"] >= Q.G
        r["5年1億_差"] = ok.mean() - ok0.mean()
        r["5年1億_差SE"] = Q.paired_se(ok, ok0) if k != "R0" else 0.0
        ok7, ok70 = p["H"] >= Q.G, ref["H"] >= Q.G
        r["7年1億_差"] = ok7.mean() - ok70.mean()
        r["7年1億_差SE"] = Q.paired_se(ok7, ok70) if k != "R0" else 0.0
        for g in GAM:
            r[f"CE{g}"] = ce(p["H60"], g)
            r[f"CE{g}_差"] = r[f"CE{g}"] - ce(ref["H60"], g)
            r[f"CE{g}_差SE"] = ce_diff_se(p["H60"], ref["H60"], g) if k != "R0" else 0.0
            r[f"7年CE{g}"] = ce(p["H"], g)
        hrows.append(r)
    print("MC", scen, round(time.time() - t0, 1), flush=True)
HH = pd.DataFrame(hrows)
HH.to_csv(f"{OUT}/household.csv", index=False, encoding="utf-8-sig")
np.savez_compressed(f"{OUT}/paths_base.npz", **{f"H60_{k}": PATHS[k]["H60"].astype(np.float64) for k in ORDER},
                    **{f"mindd60_{k}": PATHS[k]["mindd60"] for k in ORDER}, **{f"H84_{k}": PATHS[k]["H"] for k in ORDER})

# 参考：全期間（R2を除く）と従来のDC④
M = Q.draw_months(TT, 100_000, 84, seed=42)
fr = []
for k in ["旧DC④(hh.run_dc)"] + [k for k in ORDER if k != "R2"]:
    col = T[Q.D1] if k.startswith("旧") else MB[k]
    p = mc(col, M)
    s5, s7 = Q.summarize(p, 60), Q.summarize(p, 84)
    fr.append({"規則": k, "5年1億": s5["1億以上"], "7年1億": s7["1億以上"], "5年中央値": s5["中央値"], "元本割れ": s5["元本割れ"],
               "途中50超": s5["途中50超"], **{f"CE{g}": ce(p["H60"], g) for g in GAM}})
FULL = pd.DataFrame(fr)
FULL.to_csv(f"{OUT}/household_full.csv", index=False, encoding="utf-8-sig")
print(FULL.round(4).to_string(index=False), flush=True)

# 預金の感応度（共通の月、基本、5年）
M = Q.draw_months(TT, 100_000, 60, seed=42, **starts_kw("基本", lo))
ds = []
for lbl, kw in [("019・0.1%（基準）", {}), ("従来の0.1%一定", dict(dep_model="flat", rate=0.001)),
                ("018・6か月以上0.35%", dict(dep_model="019", rate=0.0035)), ("019・0.7%", dict(rate=0.007))]:
    Ms, _ = series(**kw)
    for k in ORDER:
        p = mc(Ms[k], M, months=60)
        ds.append({"預金": lbl, "規則": k, "5年1億": (p["H60"] >= Q.G).mean(), **{f"CE{g}": ce(p["H60"], g) for g in GAM}})
DS = pd.DataFrame(ds)
DS.to_csv(f"{OUT}/dep_sens.csv", index=False, encoding="utf-8-sig")
print(DS.pivot(index="規則", columns="預金", values="5年1億").reindex(ORDER).round(4).to_string(), flush=True)

# =============================================================
# 3. 64通り（起点4×遅延4×利率4）
# =============================================================
STARTS = ["2002-12-01", "2008-08-01", "2013-01-01", "2018-03-01"]
DELAYS = [4, 5, 10, 15]
RATES = [0.001, 0.003, 0.007, 0.010]
grows = []
for st, dl, rt in itertools.product(STARTS, DELAYS, RATES):
    Ms, _ = series(start=st, delay=dl, rate=rt)
    l1 = max(int(np.argmax(Ms.notna().all(axis=1).values)), int(np.searchsorted(T.index, pd.Timestamp(st))) + 1)
    assert Ms.iloc[l1:].notna().all().all()
    M = Q.draw_months(TT, 20_000, 60, seed=42, starts=np.arange(l1, TT - 11))
    for k in ORDER:
        p = mc(Ms[k], M, months=60)
        s5 = Q.summarize(p, 60)
        grows.append(dict(起点=st, 遅延=dl, 利率=rt, 規則=k, **{x: s5[x] for x in ("1億以上", "元本割れ", "途中50超")},
                          **{f"CE{g}": ce(p["H60"], g) for g in GAM}))
    print("grid", st, dl, rt, round(time.time() - t0, 1), flush=True)
GR = pd.DataFrame(grows)
GR.to_csv(f"{OUT}/grid64.csv", index=False, encoding="utf-8-sig")
gs = []
for k in ORDER:
    a = GR[GR.規則 == k].reset_index(drop=True); r = GR[GR.規則 == "R0"].reset_index(drop=True)
    gs.append(dict(規則=k, R0より確率が高い=int((a["1億以上"] > r["1億以上"] + 1e-12).sum()),
                   CE3がR0より高い=int((a["CE3"] > r["CE3"] + 1e-6).sum()),
                   制約を満たす=int(((a["元本割れ"] <= r["元本割れ"] + 1e-12) & (a["途中50超"] <= r["途中50超"] + 1e-12)).sum()),
                   確率差の平均=float((a["1億以上"] - r["1億以上"]).mean()), 確率差の最小=float((a["1億以上"] - r["1億以上"]).min()),
                   確率差の最大=float((a["1億以上"] - r["1億以上"]).max())))
GS = pd.DataFrame(gs)
GS.to_csv(f"{OUT}/grid64_summary.csv", index=False, encoding="utf-8-sig")
print(GS.round(4).to_string(index=False), flush=True)

# =============================================================
# 4. PBO（世帯レベルのCSCV）と戦略レベルのPBO、DSR
# =============================================================
S8 = 8
rowsC = np.arange(lo, TT)
chunks = np.array_split(rowsC, S8)
crow = []
for kk, comb in enumerate(itertools.combinations(range(S8), S8 // 2)):
    tr = np.zeros(TT, bool); tr[np.concatenate([chunks[c] for c in comb])] = True
    te = np.zeros(TT, bool); te[rowsC] = True; te &= ~tr
    st_tr = [s for s in range(TT - 11) if tr[s:s + 12].all()]
    st_te = [s for s in range(TT - 11) if te[s:s + 12].all()]
    Mtr = Q.draw_months(TT, 5000, 60, seed=1000 + kk, starts=st_tr)
    Mte = Q.draw_months(TT, 5000, 60, seed=2000 + kk, starts=st_te)
    ptr = {k: Q.summarize(mc(MB[k], Mtr, months=60)) for k in ORDER}
    pte = {k: Q.summarize(mc(MB[k], Mte, months=60)) for k in ORDER}
    ok_tr = [k for k in ORDER if ptr[k]["元本割れ"] <= ptr["R0"]["元本割れ"] + 1e-12 and ptr[k]["途中50超"] <= ptr["R0"]["途中50超"] + 1e-12]
    sel = max(ok_tr, key=lambda k: ptr[k]["1億以上"])
    score = {k: pte[k]["1億以上"] - (0 if (pte[k]["元本割れ"] <= pte["R0"]["元本割れ"] + 1e-12 and pte[k]["途中50超"] <= pte["R0"]["途中50超"] + 1e-12) else 1)
             for k in ORDER}
    rank = sum(score[k] < score[sel] for k in ORDER) + 1
    wv = min(max(rank / (len(ORDER) + 1), 1e-6), 1 - 1e-6)
    crow.append(dict(split=kk, 学習区間="".join(map(str, comb)), 選択=sel, 検証での順位=rank, logit=math.log(wv / (1 - wv)),
                     選択の検証1億=pte[sel]["1億以上"], R0の検証1億=pte["R0"]["1億以上"],
                     **{f"学習_{k}": ptr[k]["1億以上"] for k in ORDER}, **{f"検証_{k}": pte[k]["1億以上"] for k in ORDER}))
CS = pd.DataFrame(crow)
CS.to_csv(f"{OUT}/cscv_household.csv", index=False, encoding="utf-8-sig")
pbo_h = float((CS["logit"] <= 0).mean())
print("PBO世帯", pbo_h, CS["選択"].value_counts().to_dict(), round(time.time() - t0, 1), flush=True)

pbo_s = E.pbo_cscv(MB.iloc[lo:][ORDER].values, S=16)

# 歴史ウォーク（5年ごとに区切った実際の歴史）→ R0に対する超過 → DSR
win = [np.arange(s, min(s + 60, TT)) for s in range(lo, TT, 60)]
walk = {}
for k in ORDER:
    parts = []
    for ix in win:
        p = Q.household_mc(T_with(MB[k]), S, CAND, months=len(ix), M=ix[None, :], record=True)
        H = p["Hrec"][0]
        prev = np.concatenate([[Q.H0], H[:-1]])
        parts.append(H / (prev + 27_500 + 50_000) - 1)
    walk[k] = np.concatenate(parts)
WK = pd.DataFrame(walk, index=T.index[lo:lo + sum(len(x) for x in win)])
WK.to_csv(f"{OUT}/walk_monthly.csv")
XS = WK[ORDER].sub(WK["R0"], axis=0)
trials = [k for k in ORDER if k != "R0"]
sr = XS[trials].mean() / XS[trials].std().replace(0, np.nan)
pd_ = dict(PBO_世帯CSCV=pbo_h, PBO_DC単体_S16=float(pbo_s), PBO_歴史ウォーク_S16=float(E.pbo_cscv(WK[ORDER].values, S=16)),
           世帯CSCVで選ばれた回数=CS["選択"].value_counts().to_dict(),
           窓=[f"{T.index[ix[0]].date()}〜{T.index[ix[-1]].date()}" for ix in win], dsr={})
for k in trials:
    x = XS[k].values
    s_ = float(sr[k]) if sr[k] == sr[k] else 0.0
    for nt in (12, 12 + 169):
        pd_["dsr"][f"{k}|N={nt}"] = E.deflated_sharpe(s_, n_trials=nt, sr_var_trials=float(np.nanvar(sr.values)), T=len(x),
                                                      skew=float(skew(x)), kurt=float(kurtosis(x, fisher=False)))
    pd_["dsr"][f"{k}|超過の月次SR"] = s_
endv = {}
for k in ORDER:
    endv[k] = [round(float(Q.household_mc(T_with(MB[k]), S, CAND, months=len(ix), M=ix[None, :])["H"][0]) / 1e4) for ix in win]
pd_["窓の最後の世帯資産(万円)"] = endv
json.dump(pd_, open(f"{OUT}/pbo_dsr.json", "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps({k: v for k, v in pd_.items()}, ensure_ascii=False, indent=1, default=float), flush=True)

# =============================================================
# 5. 判定（事前固定）
# =============================================================
b = HH[HH.シナリオ == "基本"].set_index("規則")
ng = HH[HH.シナリオ == "ネガ寄せ"].set_index("規則")
gsi = GS.set_index("規則")
dec = {"判定の順": [], "PBO_世帯": pbo_h}
passed = []
for k in trials:
    g1 = bool(b.loc[k, "5年_元本割れ"] <= b.loc["R0", "5年_元本割れ"] + 1e-12 and b.loc[k, "5年_途中50超"] <= b.loc["R0", "5年_途中50超"] + 1e-12)
    g2p = bool(b.loc[k, "5年1億_差"] > 2 * b.loc[k, "5年1億_差SE"])
    g2c = {g: bool(b.loc[k, f"CE{g}_差"] > 2 * b.loc[k, f"CE{g}_差SE"]) for g in GAM}
    g3n = bool(ng.loc[k, "5年1億_差"] >= 0 and all(ng.loc[k, f"CE{g}_差"] >= 0 for g in GAM))
    g3g = bool(gsi.loc[k, "R0より確率が高い"] >= 33)
    g3p = bool(pbo_h < 0.5)
    ok = g1 and g2p and all(g2c.values()) and g3n and g3g and g3p
    dec["判定の順"].append(dict(規則=k, 制約=g1, 確率で上回る=g2p, **{f"CE{g}で上回る": v for g, v in g2c.items()},
                              ネガ寄せでR0以上=g3n, 通り64の過半=g3g, PBO50未満=g3p, 採用条件をすべて満たす=ok,
                              確率差=float(b.loc[k, "5年1億_差"]), 確率差SE=float(b.loc[k, "5年1億_差SE"])))
    if ok:
        passed.append(k)
dec["満たした規則"] = passed
dec["最終"] = max(passed, key=lambda k: b.loc[k, "5年_1億以上"]) if passed else "R0"
json.dump(dec, open(f"{OUT}/decision.json", "w"), ensure_ascii=False, indent=1, default=bool)
print(json.dumps(dec, ensure_ascii=False, indent=1, default=bool))
print("total", round(time.time() - t0, 1))
