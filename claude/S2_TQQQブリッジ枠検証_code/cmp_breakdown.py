"""D2（到達＝換金後で判定）で、世帯が初めて「税引き後1億」に届いた月の内訳。出力：out_cmp/breakdown_D2.csv"""
import sys; sys.path.insert(0, ".")
import numpy as np, pandas as pd
import cmp_common as Q
w = Q.World2("data"); T, S = Q.build_all(w)
M = Q.draw_months(len(T), 100_000, 84, seed=42)
cand = Q.CANDS["D2"]
p = Q.household_mc(T, S, cand, months=84, M=M, reach_liq=True, snap=True)
SN = p["SN"]
# 検算：同じ乱数で本計算と一致
assert abs((p["H60"] >= 1e8).mean() - 0.73492) < 1e-9, (p["H60"] >= 1e8).mean()
A = Q.ASSETS
def build(mask, label):
    n = int(mask.sum())
    lat = Q.TAU * np.maximum(SN["Wb"] - SN["Bb"] - SN["pool"], 0)
    Hb = SN["Wb"] + SN["D"] + SN["N"]                  # 売買前の評価額
    Hat = Hb - lat                                     # 税引き後
    wold, wnew = SN["wold"], SN["wnew"]
    def hold(wv, W):                                   # 銘柄別の額
        d = {a: wv[:, i] * W for i, a in enumerate(A)}
        d["円現金"] = (1 - wv.sum(1)) * W
        return d
    before = hold(wold, SN["Wb"]); after = hold(wnew, SN["Wa"])
    rows = {"到達の月（開始から）": SN["t"] + 1, "世帯の評価額（税引き前）": Hb, "含み益の税（売れば払う）": lat, "世帯の税引き後資産": Hat,
            "S2口座の評価額": SN["Wb"], "DC": SN["D"], "NISA": SN["N"]}
    for a, v in before.items(): rows[f"到達時 S2内 {a}"] = v
    rows["床つきに切替で払う税"] = SN["tax"]; rows["切替後 S2口座の評価額"] = SN["Wa"]
    for a, v in after.items(): rows[f"切替後 S2内 {a}"] = v
    df = pd.DataFrame(rows)[mask]
    out = df.describe(percentiles=[.1, .5, .9]).T[["mean", "10%", "50%", "90%"]]
    out.insert(0, "件数", n); out["区分"] = label
    return out, df
res = []
for lab, mk in [("5年以内に到達", (SN["t"] >= 0) & (SN["t"] < 60)), ("7年以内に到達", SN["t"] >= 0)]:
    o, d = build(mk, lab); res.append(o)
    if lab.startswith("5"):
        d5 = d; r5 = SN["ret"][mk]
o = pd.concat(res); o.to_csv("out_cmp/breakdown_D2.csv", encoding="utf-8-sig")
pd.set_option("display.width", 200); pd.set_option("display.float_format", lambda x: f"{x:,.1f}")
v = o[o.区分 == "5年以内に到達"].copy()
for c in ["mean", "10%", "50%", "90%"]:
    m = ~v.index.isin(["到達の月（開始から）"]); v.loc[m, c] = v.loc[m, c] / 1e4
print("到達件数(5年以内)", int(((SN['t']>=0)&(SN['t']<60)).sum()), "/ 100000, 7年以内", int((SN['t']>=0).sum()))
print(v[["mean", "10%", "50%", "90%"]].to_string())
print("到達月の K0 ×(退避)の割合", r5.mean())
print("到達月の分布(月)", np.percentile(SN["t"][(SN["t"]>=0)&(SN["t"]<60)]+1,[10,50,90]))
# 到達時の代表的な1経路（中央値に近い月に到達した経路）
mid = d5.index[(d5["到達の月（開始から）"] - d5["到達の月（開始から）"].median()).abs().argsort()[:1]]
print(d5.loc[mid].T.map(lambda x: f"{x:,.1f}").to_string())
# 今日（11/9約定後）の内訳
W0=Q.W0; gp=W0*0.5; print("今日 S2", W0/1e4, "GP", gp/1e4, "現金", W0*0.5/1e4, "DC", Q.D0/1e4, "NISA", Q.N0/1e4, "含み益税", Q.TAU*gp*Q.GP_GAIN0/1e4, "税引き後世帯", (Q.H0-Q.TAU*gp*Q.GP_GAIN0)/1e4)
