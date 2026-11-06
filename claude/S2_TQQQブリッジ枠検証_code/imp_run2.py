"""事後の組み合わせを実行し、単独候補と合わせて一次判定（税引前NAVと換金後NAVの両方）"""
import sys, time
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import imp_common as C, imp_candidates as K, s2x as X

w = C.World("data")
base_cols = None
rows, monthly, monthly_liq = [], {}, {}

def one(code, name, view, cfg, policy, jkey):
    r = w.run(cfg, policy, jkey=jkey)
    ev, T = C.evaluate(w, r, jkey=jkey)
    ml = X.indicators(r["nav_liq"])
    ml1 = X.indicators(X.sub(r["nav_liq"], *C.TRAIN)); ml2 = X.indicators(X.sub(r["nav_liq"], *C.TEST))
    ev.update(L_CAGR=ml["CAGR"], L_Sortino=ml["Sortino"], L_MaxDD=ml["MaxDD"], L_MaxDD_date=ml["MaxDD_date"],
              L_CAGR_h1=ml1["CAGR"], L_CAGR_h2=ml2["CAGR"])
    rows.append(dict(code=code, name=name, view=view, **ev))
    monthly[code] = T["S2"]
    monthly_liq[code] = r["nav_liq"].resample("ME").last().pct_change().dropna()

one("S2元", "S2（元エンジン：最初の持ち替えまで円現金）", "基準", dict(start_invested=False), None, "base")
one("S2", "S2（修正版：初日から投資）＝比較の基準", "基準", {}, None, "base")
for c in K.CANDIDATES + K.COMBOS:
    one(c["code"], c["name"], c["view"], c["cfg"], c["policy"], c["judg"])

df = pd.DataFrame(rows)
b = df.set_index("code").loc["S2"]
for k in ["CAGR", "CAGR_h1", "CAGR_h2", "p5", "p5_neg", "p5_hist", "p7", "Sortino", "MaxDD", "L_CAGR", "L_CAGR_h1", "L_CAGR_h2", "L_MaxDD", "L_Sortino"]:
    df["d_" + k] = df[k] - b[k]
DD_LIMIT = -0.36108059419177385
df["合格_年率"] = df["d_CAGR"] > 0
df["合格_5年1億"] = df["d_p5"] > 0
df["合格_ソルティノ"] = df["Sortino"] >= 0.82
df["合格_最大下落"] = df["MaxDD"] >= DD_LIMIT - 1e-12
df["合格_前後半"] = (df["d_CAGR_h1"] > 0) & (df["d_CAGR_h2"] > 0)
df["一次合格_税引前"] = df[["合格_年率", "合格_5年1億", "合格_ソルティノ", "合格_最大下落", "合格_前後半"]].all(axis=1)
# 換金後NAVで測った場合（最大下落は基準S2の換金後 −27.9% より悪化しない）
df["合格L_最大下落"] = df["L_MaxDD"] >= b["L_MaxDD"] - 1e-12
df["合格L_前後半"] = (df["d_L_CAGR_h1"] > 0) & (df["d_L_CAGR_h2"] > 0)
df["一次合格_換金後"] = (df["d_L_CAGR"] > 0) & df["合格_5年1億"] & (df["L_Sortino"] >= 0.82) & df["合格L_最大下落"] & df["合格L_前後半"]
df.to_csv("out_imp/candidates_all.csv", index=False)
pd.DataFrame(monthly).to_csv("out_imp/monthly_all.csv")
pd.DataFrame(monthly_liq).to_csv("out_imp/monthly_liq_all.csv")
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
show = ["code", "CAGR", "d_CAGR", "Sortino", "MaxDD", "d_CAGR_h1", "d_CAGR_h2", "p5", "d_p5", "L_CAGR", "L_MaxDD", "d_L_CAGR_h1", "d_L_CAGR_h2", "trades", "一次合格_税引前", "一次合格_換金後"]
print(df[show].round(4).to_string(index=False))
