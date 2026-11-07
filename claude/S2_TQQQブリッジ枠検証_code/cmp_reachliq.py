"""
判定の再確認：「到達（1億）」を換金後（評価額−S2の含み益の税）で判定する定義で、全部をやり直す（事後の確認）。
理由：到達したら売って守りに入る規則では、評価額で1億に届いた瞬間に売ると税で1億を割り、翌月に買い戻す往復が起きる。
     「売って税を払っても1億残る」で到達とするのが規則として一貫する。
出力：out_cmp/reachliq_household.csv、reachliq_decision.json、reachliq_cscv.json、reachliq_grid48.csv、reachliq_stress.csv
"""
import sys, json, math, time, itertools
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import cmp_common as Q

OUT = "out_cmp"
t0 = time.time()
w = Q.World2("data")
T, S = Q.build_all(w)
TT = len(T)
ORDER = Q.ORDER
RL = dict(reach_liq=True)

# ---------------- 1. 本計算（10万本・84ヶ月、本計算と同じ乱数） ----------------
res, P = [], {}
for scen in ("基本", "ネガ寄せ", "直近"):
    M = Q.draw_months(TT, 100_000, 84, seed=42, **Q.scen_kw(T, scen))
    for c in ORDER:
        p = Q.household_mc(T, S, Q.CANDS[c], months=84, M=M, **RL)
        P[(scen, c)] = p
        for hz in (60, 84):
            res.append(dict(シナリオ=scen, 期間=hz, 候補=c, 名前=Q.CANDS[c]["name"], **Q.summarize(p, hz)))
    print(scen, round(time.time() - t0, 1), flush=True)
hh = pd.DataFrame(res)
hh.to_csv(f"{OUT}/reachliq_household.csv", index=False)
b5 = hh[(hh.シナリオ == "基本") & (hh.期間 == 60)].set_index("候補")
ok = {c: P[("基本", c)]["H60"] >= 1e8 for c in ORDER}


def decide(perf, pool, okd):
    ref = perf.loc["A1"]
    passed = [c for c in pool if perf.loc[c, "元本割れ"] <= ref["元本割れ"] + 1e-12 and perf.loc[c, "途中50超"] <= ref["途中50超"] + 1e-12]
    rank = sorted(passed, key=lambda c: -perf.loc[c, "1億以上"])
    best = rank[0]
    se = {c: Q.paired_se(okd[best], okd[c]) for c in rank if c != best}
    ties = [best] + [c for c in rank if c != best and perf.loc[best, "1億以上"] - perf.loc[c, "1億以上"] < 2 * se[c]]
    chosen = max(ties, key=lambda c: perf.loc[c, "1億以上の平均"])
    return dict(制約を満たす=passed, 確率の順=[(c, float(perf.loc[c, "1億以上"])) for c in rank],
                一位との差と対の標準誤差={c: (float(perf.loc[best, "1億以上"] - perf.loc[c, "1億以上"]), se[c]) for c in se},
                同点=ties, 上振れ_1億以上の平均={c: float(perf.loc[c, "1億以上の平均"]) for c in ties}, 選択=chosen)


dec = dict(事前登録11=decide(b5, Q.ORDER_PRE, ok), 事後を含む13=decide(b5, ORDER, ok))
# 関門：ネガ寄せ・換金後
gate = {}
for c in ("C3", "D2"):
    pn, pa = P[("ネガ寄せ", c)], P[("ネガ寄せ", "A1")]
    se_n = Q.paired_se(pn["H60"] >= 1e8, pa["H60"] >= 1e8)
    pb, pab = P[("基本", c)], P[("基本", "A1")]
    se_l = Q.paired_se(pb["H60L"] >= 1e8, pab["H60L"] >= 1e8)
    gate[c] = dict(ネガ寄せ=bool((pn["H60"] >= 1e8).mean() >= (pa["H60"] >= 1e8).mean() - 2 * se_n),
                   換金後=bool((pb["H60L"] >= 1e8).mean() >= (pab["H60L"] >= 1e8).mean() - 2 * se_l))
dec["関門_ネガ寄せと換金後"] = gate
# C3とD2の対比較（シナリオ・期間ごと）
pair = []
for scen in ("基本", "ネガ寄せ", "直近"):
    for hz, key in ((60, "H60"), (84, "H")):
        a = P[(scen, "C3")][key] >= 1e8; b = P[(scen, "D2")][key] >= 1e8
        pair.append(dict(シナリオ=scen, 期間=hz, C3=a.mean(), D2=b.mean(), 差_C3マイナスD2=a.mean() - b.mean(), 対の標準誤差=Q.paired_se(a, b)))
dec["C3対D2"] = pair
json.dump(dec, open(f"{OUT}/reachliq_decision.json", "w"), ensure_ascii=False, indent=1, default=float)
print(json.dumps(dec, ensure_ascii=False, indent=1, default=float), flush=True)

# ---------------- 2. 世帯CSCV（70通り） ----------------
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
        a = Q.household_mc(T, S, Q.CANDS[c], months=60, M=Mtr, **RL)
        b = Q.household_mc(T, S, Q.CANDS[c], months=60, M=Mte, **RL)
        ptr[c], pte[c] = Q.summarize(a), Q.summarize(b)
        oktr[c] = a["H60"] >= 1e8
    perf_tr = pd.DataFrame(ptr).T
    for pool_name, pool in (("事前登録11", Q.ORDER_PRE), ("事後を含む13", ORDER)):
        sel = decide(perf_tr, pool, oktr)["選択"]
        ref = pte["A1"]
        score = {c: pte[c]["1億以上"] - (0 if (pte[c]["元本割れ"] <= ref["元本割れ"] + 1e-12 and pte[c]["途中50超"] <= ref["途中50超"] + 1e-12) else 1)
                 for c in pool}
        n = len(pool)
        rank = sum(score[c] < score[sel] for c in pool) + 1
        wv = min(max(rank / (n + 1), 1e-6), 1 - 1e-6)
        rows.append(dict(split=k, 母集団=pool_name, 選択=sel, 検証での順位=rank, logit=math.log(wv / (1 - wv)),
                         C3=pte["C3"]["1億以上"], D2=pte["D2"]["1億以上"], A1=pte["A1"]["1億以上"],
                         C3元本割れ=pte["C3"]["元本割れ"], D2元本割れ=pte["D2"]["元本割れ"]))
    if k % 10 == 0:
        print("cscv", k, round(time.time() - t0, 1), flush=True)
cs = pd.DataFrame(rows)
cs.to_csv(f"{OUT}/reachliq_cscv.csv", index=False)
csum = {}
for pn, d in cs.groupby("母集団"):
    dd = d.drop_duplicates("split")
    csum[pn] = dict(PBO=float((d["logit"] <= 0).mean()), 選ばれた回数=d["選択"].value_counts().to_dict(),
                    D2がC3以上の割合=float((dd["D2"] >= dd["C3"]).mean()), C3がA1以上の割合=float((dd["C3"] >= dd["A1"]).mean()),
                    D2がA1以上の割合=float((dd["D2"] >= dd["A1"]).mean()),
                    差_C3マイナスD2の中央値=float((dd["C3"] - dd["D2"]).median()))
json.dump(csum, open(f"{OUT}/reachliq_cscv.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(csum, ensure_ascii=False, indent=1), flush=True)

# ---------------- 3. 48通り（A1・C3・D2・A0） ----------------
STARTS = ["2000-04-01", "2002-10-01", "2007-10-01", "2013-01-01"]
g_rows = []
for st, cst, lag in itertools.product(STARTS, [0.0, 0.0025, 0.005], [1, 2, 3, 5]):
    Sv = {}
    for name in ("K0_遅れ", "K0_予定どおり", "K0_先行", "K0_到達"):
        z = Q.run_series(w, Q.SPECS[name], pretax=True, start=st, slippage=cst, exec_lag=lag)
        Sv[name] = dict(r=z["r"].reindex(T.index).values, f=z["f"].reindex(T.index).fillna(0).values,
                        wt=z["wt"].reindex(T.index).fillna(0).values)
    lo = max(int(np.argmax(~np.isnan(v["r"]))) for v in Sv.values())
    for v in Sv.values():
        v["r"] = np.nan_to_num(v["r"])
    M = Q.draw_months(TT, 20000, 60, starts=np.arange(lo, TT - 11))
    for c in ("A0", "A1", "C3", "D2"):
        s_ = Q.summarize(Q.household_mc(T, Sv, Q.CANDS[c], months=60, M=M, **RL))
        g_rows.append(dict(起点=st, コスト=cst, ラグ=lag, 候補=c, **{k: s_[k] for k in ("1億以上", "元本割れ", "途中50超", "1億以上の平均", "換金後1億以上")}))
g = pd.DataFrame(g_rows)
g.to_csv(f"{OUT}/reachliq_grid48.csv", index=False)
piv = g.pivot_table(index=["起点", "コスト", "ラグ"], columns="候補", values="1億以上")
gsum = dict(D2がC3以上=int((piv["D2"] >= piv["C3"]).sum()), C3がA1より高い=int((piv["C3"] > piv["A1"]).sum()),
            D2がA1より高い=int((piv["D2"] > piv["A1"]).sum()), 差_C3マイナスD2の平均=float((piv["C3"] - piv["D2"]).mean()),
            差_C3マイナスD2の最小=float((piv["C3"] - piv["D2"]).min()), 差_C3マイナスD2の最大=float((piv["C3"] - piv["D2"]).max()))
json.dump(gsum, open(f"{OUT}/reachliq_grid48_summary.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(gsum, ensure_ascii=False, indent=1), flush=True)

# ---------------- 4. 暴落ストレス ----------------
M = Q.draw_months(TT, 100_000, 60)
st_rows = []
for lbl, jp in [("なし", None), ("1日−20%", dict(p=1 / 480, J=-0.20)), ("1日−25%", dict(p=1 / 480, J=-0.25)),
                ("TQQQ全損", dict(p=1 / 480, J=-0.25, total_loss=True))]:
    for c in ("A0", "A1", "C3", "D2", "B1"):
        s_ = Q.summarize(Q.household_mc(T, S, Q.CANDS[c], months=60, M=M, jump=jp, **RL))
        st_rows.append(dict(ストレス=lbl, 候補=c, **{k: s_[k] for k in ("1億以上", "元本割れ", "途中30超", "途中50超", "悪いほう5%")}))
pd.DataFrame(st_rows).to_csv(f"{OUT}/reachliq_stress.csv", index=False)
print(pd.DataFrame(st_rows).pivot(index="候補", columns="ストレス", values="途中50超").round(4).to_string())
print("total", round(time.time() - t0, 1))
