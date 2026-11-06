# 促進の要因（技法39）：S2の稼ぎを「状態×ブレーキ」に分解し、各局面で別の持ち物だったらどうだったかを測る
import sys; sys.path.insert(0, '.')
import numpy as np, pandas as pd, s2engine as E, hh
mkt = hh.load_all("data"); assets = E.build_assets(mkt); judg = E.judge_states(mkt)
s2 = E.simulate(mkt, assets, judg, E.Cfg())
nav = s2["nav"]; st = s2["states"]
r = nav.pct_change().fillna(0.0)
# その日のリターンを生んだ持ち物は前日の状態（執行は翌営業日）
reg = st["state"].shift(1).fillna("NORMAL") + np.where(st["braked"].shift(1).fillna(False), "_brk", "")
lr = np.log1p(r)
yrs = (nav.index[-1] - nav.index[0]).days / 365.25
alt = {k: np.log1p(assets.loc[nav.index, k]) for k in ["GP", "N1", "SV", "TQQQ", "QQQ1"]}
rows = []
for g, idx in reg.groupby(reg).groups.items():
    rows.append(dict(局面=g, 日数=len(idx), 年数=len(idx) / 252, S2対数リターン計=lr[idx].sum(),
                     年率寄与=lr[idx].sum() / yrs, 局面内年率=np.expm1(lr[idx].sum() / (len(idx) / 252)),
                     GPなら=alt["GP"][idx].sum(), N1なら=alt["N1"][idx].sum(), SVなら=alt["SV"][idx].sum(),
                     TQQQなら=alt["TQQQ"][idx].sum(), 下落日の標準偏差=r[idx][r[idx] < 0].std() * np.sqrt(252)))
df = pd.DataFrame(rows).sort_values("日数", ascending=False)
df.to_csv("out_imp/decomp_regimes.csv", index=False)
pd.set_option("display.width", 250)
print(df.round(4).to_string(index=False))
print("合計対数", lr.sum(), "年率", np.expm1(lr.sum() / yrs))
# 年別：S2とGP持ちっぱなし、為替の年変化
y = pd.DataFrame({"S2": nav.resample("YE").last().pct_change(),
                  "GP": (1 + assets["GP"]).cumprod().loc[nav.index].resample("YE").last().pct_change(),
                  "USDJPY": mkt["fx"].loc[nav.index].resample("YE").last().pct_change(),
                  "QQQ_usd": mkt["qqq"].loc[nav.index].resample("YE").last().pct_change(),
                  "金_usd": mkt["gold"].loc[nav.index].resample("YE").last().pct_change()})
print(y.round(3).to_string())
