"""
目標ルールの数字が前回（77.2%）から今回（70.6%）へ下がった要因の分解。前回と同じ乱数（2万本・60ヶ月・基本）。
  段1 前回の近似を新エンジンで再現（S2月次×L/2、税なし、濃さは毎月どこへでも）＝前回値と一致するはず
  段2 ＋濃さは月1回・1段階（G5の仕様）
  段3 ＋仕様どおりの持ち物（各濃さを日次バックテスト。税は過去の実績どおり系列に含む）
  段4 ＋税を経路ごとに計算（税引前の系列＋取得額の追跡。今の含み益35%★の初期売却税を含む）＝今回の値
  段4' 段4で初期の含み益0（初期売却税なし）
  段5 段4＋「到達」を換金後（評価額−含み益の税）で判定（事後の改良案の確認用）
出力：out_cmp/decomp_goal.csv
"""
import sys
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import cmp_common as Q, hh

w = Q.World2("data")
T, S = Q.build_all(w)
TT = len(T)
# 段1用：前回の近似（K0の課税後月次×L/2）
s2 = T["S2"].values; ret = T["RET"].values > 0.5; rate = T["RATE"].values
def scaled(L, lev_cost=0.03):
    r_on = (L / 2.0) * s2 - (max(L - 1, 0) - L / 2.0) * rate / 12 - max(L - 2, 0) * lev_cost / 12
    return np.where(ret, s2, r_on)
Sx = dict(S)
gp_w = np.zeros((TT, len(Q.ASSETS))); gp_w[:, 0] = 1.0
for L in (2.5, 2.0, 1.2, 0.5):
    Sx[f"OLD_L{L}"] = dict(r=scaled(L), f=np.zeros(TT), wt=gp_w)
# 段3用：各濃さの課税後系列（過去の税を含む）
for k in ("K0_遅れ", "K0_予定どおり", "K0_先行", "K0_到達"):
    z = Q.run_series(w, Q.SPECS[k], pretax=False)
    Sx[k + "_tax"] = dict(r=z["r"].reindex(T.index).values, f=np.zeros(TT), wt=z["wt"].reindex(T.index).fillna(0).values)

M = Q.draw_months(TT, 20000, 60)
kw_old = dict(dc_col=Q.D1, cS2=0, cN=50_000, W0=Q.W0, D0=Q.D0, N0=Q.N0)
rows = []
def rec(lbl, code, p):
    H = p["H"]
    rows.append(dict(段=lbl, 候補=code, 一億以上=(H >= 1e8).mean(), 一度でも=p["hit"].mean(), 元本割れ=(H < Q.H0).mean(),
                     途中50超=(p["mindd"] <= -0.5).mean(), 中央値=np.median(H), 換金後一億以上=(p["HL"] >= 1e8).mean()))
for code, beh in (("A0", None), ("A1", 2.5), ("A2", 2.0)):
    goal = code != "A0"
    po = hh.hh_mc(T, return_paths=True, months=60, goal=goal, behind=beh or 2.5, **kw_old)
    rows.append(dict(段="0 前回の値（hh.py）", 候補=code, 一億以上=(po["H"] >= 1e8).mean(), 一度でも=po["hit"].mean(),
                     元本割れ=(po["H"] < Q.H0).mean(), 途中50超=(po["mindd"] <= -0.5).mean(), 中央値=np.median(po["H"]), 換金後一億以上=np.nan))
    if goal:
        lv_old = (f"OLD_L{beh}", "OLD_L2.0", "OLD_L1.2", "OLD_L0.5")
    else:
        lv_old = ("OLD_L2.0",) * 4
    c_old = dict(sleeves=[(1.0, lv_old)], overlay="goal" if goal else "none")
    rec("1 前回の近似を再現", code, Q.household_mc(T, Sx, c_old, months=60, M=M, tax=False, one_step=False, gp_gain0=0.0))
    rec("2 ＋月1回・1段階", code, Q.household_mc(T, Sx, c_old, months=60, M=M, tax=False, one_step=True, gp_gain0=0.0))
    levs = Q.CANDS[code]["sleeves"][0][1]
    c_tax = dict(sleeves=[(1.0, tuple(x + "_tax" for x in levs))], overlay=Q.CANDS[code]["overlay"])
    rec("3 ＋仕様どおりの持ち物（税は過去実績）", code, Q.household_mc(T, Sx, c_tax, months=60, M=M, tax=False, gp_gain0=0.0))
    rec("4 ＋税を経路ごと（今回）", code, Q.household_mc(T, Sx, Q.CANDS[code], months=60, M=M))
    rec("4' 段4で初期含み益0", code, Q.household_mc(T, Sx, Q.CANDS[code], months=60, M=M, gp_gain0=0.0))
    if goal:
        rec("5 段4＋到達を換金後で判定", code, Q.household_mc(T, Sx, Q.CANDS[code], months=60, M=M, reach_liq=True))
d = pd.DataFrame(rows)
d.to_csv("out_cmp/decomp_goal.csv", index=False)
pd.set_option("display.width", 250)
print(d.round(4).to_string(index=False))
