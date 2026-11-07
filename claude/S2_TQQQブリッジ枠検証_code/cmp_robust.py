"""
世帯の候補比較：頑健性と関門（cmp_prereg.py の判定4）。出力：out_cmp/
  cscv_household.csv / cscv_summary.json  世帯レベルのCSCV（318ヶ月を8区間、学習4・検証4の70通り）
  walk_monthly.csv / pbo_dsr.json         実際の歴史を5年ごとに区切って起点から走らせた月次（時間加重）→ CSCV(S=16)とDSR
  grid48.csv / grid48_summary.csv         起点4×コスト3×執行ラグ4。各通りで同じ物差しのMC（2万本・5年）
  stress.csv                              1日の暴落ストレス（−20%、−25%、TQQQ全損）
  sens.csv                                含み益の仮定（0%・50%）、到達を換金後で判定
  decision_final.json                     関門を通した最終の選択
"""
import sys, json, math, time, itertools
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from scipy.stats import skew, kurtosis
import cmp_common as Q, s2engine as E

OUT = "out_cmp"
t0 = time.time()
w = Q.World2("data")
T, S = Q.build_all(w)
TT = len(T)
ORDER = Q.ORDER
dec_main = json.load(open(f"{OUT}/decision_main.json"))


def decide(perf, pool, ok=None):
    """perf[c] = summarize の dict。判定1〜3。ok: 経路別の1億以上（同点判定の対の標準誤差用）。"""
    ref = perf["A1"]
    passed = [c for c in pool if perf[c]["元本割れ"] <= ref["元本割れ"] + 1e-12 and perf[c]["途中50超"] <= ref["途中50超"] + 1e-12]
    rank = sorted(passed, key=lambda c: -perf[c]["1億以上"])
    best = rank[0]
    if ok is None:
        return best
    ties = [c for c in rank if c == best or perf[best]["1億以上"] - perf[c]["1億以上"] < 2 * Q.paired_se(ok[best], ok[c])]
    return max(ties, key=lambda c: perf[c]["1億以上の平均"])


# =============================================================
# 1. 世帯レベルのCSCV（PBO）
# =============================================================
S8 = 8
chunks = np.array_split(np.arange(TT), S8)
rows = []
for k, comb in enumerate(itertools.combinations(range(S8), S8 // 2)):
    tr = np.zeros(TT, bool); tr[np.concatenate([chunks[c] for c in comb])] = True
    te = ~tr
    st_tr = [s for s in range(TT - 11) if tr[s:s + 12].all()]
    st_te = [s for s in range(TT - 11) if te[s:s + 12].all()]
    Mtr = Q.draw_months(TT, 5000, 60, seed=1000 + k, starts=st_tr)
    Mte = Q.draw_months(TT, 5000, 60, seed=2000 + k, starts=st_te)
    ptr, pte, oktr = {}, {}, {}
    for c in ORDER:
        a = Q.household_mc(T, S, Q.CANDS[c], months=60, M=Mtr)
        b = Q.household_mc(T, S, Q.CANDS[c], months=60, M=Mte)
        ptr[c], pte[c] = Q.summarize(a), Q.summarize(b)
        oktr[c] = a["H60"] >= 1e8
    for pool_name, pool in (("事前登録11", Q.ORDER_PRE), ("事後を含む13", ORDER)):
        sel = decide(ptr, pool, oktr)
        ref = pte["A1"]
        score = {c: pte[c]["1億以上"] - (0 if (pte[c]["元本割れ"] <= ref["元本割れ"] + 1e-12 and pte[c]["途中50超"] <= ref["途中50超"] + 1e-12) else 1)
                 for c in pool}
        n = len(pool)
        rank = sum(score[c] < score[sel] for c in pool) + 1
        wv = min(max(rank / (n + 1), 1e-6), 1 - 1e-6)
        rows.append(dict(split=k, 学習区間="".join(str(c) for c in comb), 母集団=pool_name, 選択=sel, 検証での順位=rank, 候補数=n,
                         logit=math.log(wv / (1 - wv)), 選択の検証1億以上=pte[sel]["1億以上"], A1の検証1億以上=pte["A1"]["1億以上"],
                         C3の検証1億以上=pte["C3"]["1億以上"], D2の検証1億以上=pte["D2"]["1億以上"],
                         **{f"学習_{c}": ptr[c]["1億以上"] for c in ORDER}))
    if k % 10 == 0:
        print("cscv", k, round(time.time() - t0, 1), flush=True)
cs = pd.DataFrame(rows)
cs.to_csv(f"{OUT}/cscv_household.csv", index=False)
cs_sum = {}
for pn, d in cs.groupby("母集団"):
    cs_sum[pn] = dict(PBO=float((d["logit"] <= 0).mean()), 分割数=len(d),
                      選ばれた回数=d["選択"].value_counts().to_dict(),
                      選択が検証でA1以上の割合=float((d["選択の検証1億以上"] >= d["A1の検証1億以上"]).mean()),
                      C3が検証でA1以上の割合=float((d["C3の検証1億以上"] >= d["A1の検証1億以上"]).mean()),
                      D2が検証でA1以上の割合=float((d["D2の検証1億以上"] >= d["A1の検証1億以上"]).mean()),
                      選択の検証順位の中央値=float(d["検証での順位"].median()))
json.dump(cs_sum, open(f"{OUT}/cscv_summary.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(cs_sum, ensure_ascii=False, indent=1), flush=True)

# =============================================================
# 2. 実際の歴史を5年ごとに（起点4,858.6万から）走らせた月次 → CSCV(S=16) と DSR
# =============================================================
win = [np.arange(s, min(s + 60, TT)) for s in range(0, TT, 60)]
walk = {}
for c in ORDER:
    parts = []
    for ix in win:
        p = Q.household_mc(T, S, Q.CANDS[c], months=len(ix), M=ix[None, :], record=True)
        H = p["Hrec"][0]
        prev = np.concatenate([[Q.H0], H[:-1]])
        parts.append(H / (prev + 27_500 + 50_000) - 1)
    walk[c] = np.concatenate(parts)
WK = pd.DataFrame(walk, index=T.index)
WK.to_csv(f"{OUT}/walk_monthly.csv")
X = WK[ORDER].sub(WK["A1"], axis=0)                 # A1（専門家の選択）に対する超過
trials = [c for c in ORDER if c != "A1"]
pbo_walk = E.pbo_cscv(WK[ORDER].values, S=16)
sr = X[trials].mean() / X[trials].std().replace(0, np.nan)
pd_ = dict(PBO_歴史ウォーク_S16=pbo_walk, 月数=len(WK), 試行数=len(ORDER), dsr={})
for c in ("C3", "D2", "A0", "D1"):
    x = X[c].values
    s_ = float(sr[c]) if sr[c] == sr[c] else 0.0
    for nt in (len(ORDER), len(ORDER) + 147):
        pd_["dsr"][f"{c}|N={nt}"] = E.deflated_sharpe(s_, n_trials=nt, sr_var_trials=float(np.nanvar(sr.values)), T=len(x),
                                                       skew=float(skew(x)), kurt=float(kurtosis(x, fisher=False)))
    pd_["dsr"][f"{c}|超過の月次SR"] = s_
    pd_["dsr"][f"{c}|差がある月数"] = int((np.abs(x) > 1e-9).sum())
# 窓ごとの5年末の世帯（実際の歴史）
endv = {}
for c in ORDER:
    vals = []
    for ix in win:
        p = Q.household_mc(T, S, Q.CANDS[c], months=len(ix), M=ix[None, :])
        vals.append(float(p["H"][0]))
    endv[c] = vals
pd_["窓の期間"] = [f"{T.index[ix[0]].date()}〜{T.index[ix[-1]].date()}" for ix in win]
pd_["窓の最後の世帯資産(万円)"] = {c: [round(v / 1e4) for v in endv[c]] for c in ORDER}
json.dump(pd_, open(f"{OUT}/pbo_dsr.json", "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps({k: v for k, v in pd_.items() if k != "窓の最後の世帯資産(万円)"}, ensure_ascii=False, indent=1, default=float), flush=True)

# =============================================================
# 3. 48通り（起点4×コスト3×執行ラグ4）
# =============================================================
STARTS = ["2000-04-01", "2002-10-01", "2007-10-01", "2013-01-01"]
COSTS = [0.0, 0.0025, 0.005]
LAGS = [1, 2, 3, 5]
g_rows = []
for st, cst, lag in itertools.product(STARTS, COSTS, LAGS):
    Sv = {}
    for name, sp in Q.SPECS.items():
        z = Q.run_series(w, sp, pretax=True, start=st, slippage=cst, exec_lag=lag)
        Sv[name] = dict(r=z["r"].reindex(T.index).values, f=z["f"].reindex(T.index).fillna(0).values,
                        wt=z["wt"].reindex(T.index).fillna(0).values)
    Sv["CASH"] = S["CASH"]
    lo = max(int(np.argmax(~np.isnan(v["r"]))) for k, v in Sv.items() if k != "CASH")
    for v in Sv.values():
        v["r"] = np.nan_to_num(v["r"])
    M = Q.draw_months(TT, 20000, 60, starts=np.arange(lo, TT - 11))
    for c in ORDER:
        s_ = Q.summarize(Q.household_mc(T, Sv, Q.CANDS[c], months=60, M=M))
        g_rows.append(dict(起点=st, コスト=cst, ラグ=lag, 候補=c, **{k: s_[k] for k in ("1億以上", "元本割れ", "途中50超", "1億以上の平均", "換金後1億以上")}))
    print("grid", st, cst, lag, round(time.time() - t0, 1), flush=True)
g = pd.DataFrame(g_rows)
g.to_csv(f"{OUT}/grid48.csv", index=False)
gs = []
for c in ORDER:
    a = g[g.候補 == c].reset_index(drop=True); r = g[g.候補 == "A1"].reset_index(drop=True); a0 = g[g.候補 == "A0"].reset_index(drop=True)
    cons = (a["元本割れ"] <= r["元本割れ"] + 1e-12) & (a["途中50超"] <= r["途中50超"] + 1e-12)
    gs.append(dict(候補=c, A1より確率が高い=int((a["1億以上"] > r["1億以上"] + 1e-12).sum()), 制約を満たす=int(cons.sum()),
                   両方=int(((a["1億以上"] > r["1億以上"] + 1e-12) & cons).sum()), A0より確率が高い=int((a["1億以上"] > a0["1億以上"] + 1e-12).sum()),
                   確率差の平均_対A1=float((a["1億以上"] - r["1億以上"]).mean()), 確率差の最小_対A1=float((a["1億以上"] - r["1億以上"]).min()),
                   換金後でA1より高い=int((a["換金後1億以上"] > r["換金後1億以上"] + 1e-12).sum())))
gsum = pd.DataFrame(gs)
gsum.to_csv(f"{OUT}/grid48_summary.csv", index=False)
print(gsum.round(4).to_string(index=False), flush=True)

# =============================================================
# 4. 暴落ストレス（同じ乱数・10万本・5年）
# =============================================================
M = Q.draw_months(TT, 100_000, 60)
st_rows = []
for lbl, jp in [("なし", None), ("1日−20%（40年に1回）", dict(p=1 / 480, J=-0.20)), ("1日−25%（40年に1回）", dict(p=1 / 480, J=-0.25)),
                ("TQQQ全損（40年に1回、他は−25%）", dict(p=1 / 480, J=-0.25, total_loss=True))]:
    for c in ORDER:
        s_ = Q.summarize(Q.household_mc(T, S, Q.CANDS[c], months=60, M=M, jump=jp))
        st_rows.append(dict(ストレス=lbl, 候補=c, **{k: s_[k] for k in ("1億以上", "元本割れ", "途中30超", "途中50超", "悪いほう10%", "悪いほう5%")}))
stdf = pd.DataFrame(st_rows)
stdf.to_csv(f"{OUT}/stress.csv", index=False)
print(stdf.pivot(index="候補", columns="ストレス", values="途中50超").reindex(ORDER).round(4).to_string(), flush=True)

# =============================================================
# 5. 感応度：今の含み益の仮定、到達を換金後で判定
# =============================================================
sens = []
for lbl, kw in [("含み益0%", dict(gp_gain0=0.0)), ("含み益35%（基準）", {}), ("含み益50%", dict(gp_gain0=0.5)), ("到達を換金後で判定", dict(reach_liq=True))]:
    for c in ORDER:
        s_ = Q.summarize(Q.household_mc(T, S, Q.CANDS[c], months=60, M=M, **kw))
        sens.append(dict(感応度=lbl, 候補=c, **{k: s_[k] for k in ("1億以上", "元本割れ", "途中50超", "1億以上の平均", "換金後1億以上")}))
sdf = pd.DataFrame(sens)
sdf.to_csv(f"{OUT}/sens.csv", index=False)
print(sdf.pivot(index="候補", columns="感応度", values="1億以上").reindex(ORDER).round(4).to_string(), flush=True)

# =============================================================
# 6. 関門（判定4）
# =============================================================
hh = pd.read_csv(f"{OUT}/household.csv")
pM = {c: Q.household_mc(T, S, Q.CANDS[c], months=60, M=M) for c in ORDER}
Mn = Q.draw_months(TT, 100_000, 60, **Q.scen_kw(T, "ネガ寄せ"))
pN = {c: Q.household_mc(T, S, Q.CANDS[c], months=60, M=Mn) for c in ORDER}


def gates(c, pool_name):
    a = dict()
    se_n = Q.paired_se(pN[c]["H60"] >= 1e8, pN["A1"]["H60"] >= 1e8)
    a["ネガ寄せ"] = bool((pN[c]["H60"] >= 1e8).mean() >= (pN["A1"]["H60"] >= 1e8).mean() - 2 * se_n)
    se_l = Q.paired_se(pM[c]["H60L"] >= 1e8, pM["A1"]["H60L"] >= 1e8)
    a["換金後"] = bool((pM[c]["H60L"] >= 1e8).mean() >= (pM["A1"]["H60L"] >= 1e8).mean() - 2 * se_l)
    a["PBO<50%"] = bool(cs_sum[pool_name]["PBO"] < 0.5)
    ok = True
    for lbl in stdf["ストレス"].unique():
        if lbl == "なし":
            continue
        d = stdf[stdf.ストレス == lbl].set_index("候補")
        ok &= bool(d.loc[c, "元本割れ"] <= d.loc["A1", "元本割れ"] + 1e-12 and d.loc[c, "途中50超"] <= d.loc["A1", "途中50超"] + 1e-12)
    a["暴落ストレスで制約"] = ok
    return a


final = {}
for pool_name, pool in (("事前登録11", Q.ORDER_PRE), ("事後を含む13", ORDER)):
    order = [c for c, _ in dec_main[pool_name]["確率の順"]]
    trail = []
    chosen = "A1"
    for c in order:
        gt = gates(c, pool_name)
        trail.append(dict(候補=c, 関門=gt))
        if all(gt.values()):
            chosen = c
            break
    final[pool_name] = dict(順に確認=trail, 最終の選択=chosen)
json.dump(final, open(f"{OUT}/decision_final.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(final, ensure_ascii=False, indent=1))
print("total", round(time.time() - t0, 1))
