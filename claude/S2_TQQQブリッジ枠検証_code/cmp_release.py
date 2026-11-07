"""D2の床を5年（60ヶ月）で外すか。7年・10年で比較。出力 out_cmp/release_D2.csv"""
import sys; sys.path.insert(0, ".")
import numpy as np, pandas as pd, cmp_common as Q
w = Q.World2("data"); T, S = Q.build_all(w)
rows = []
for scen in ("基本", "ネガ寄せ", "直近"):
    M = Q.draw_months(len(T), 100_000, 120, seed=42, **Q.scen_kw(T, scen))
    for lab, cand, kw in [("S2（K0のまま）", "A0", {}), ("D2 床を外さない", "D2", {}), ("D2 5年で床を外す", "D2", dict(release_at=60)), ("D2 5年で届いていれば外す・未達は7年で外す", "D2", dict(release_cond=True))]:
        p = Q.household_mc(T, S, Q.CANDS[cand], months=120, M=M, reach_liq=True, record=True, **kw)
        Hr = p["Hrec"]
        if scen == "基本" and cand == "D2" and not kw:
            assert abs((Hr[:, 59] >= 1e8).mean() - 0.73492) < 0.01
        for hz in (60, 84, 120):
            H = Hr[:, hz - 1]
            pk = np.maximum.accumulate(np.concatenate([np.full((len(H), 1), Q.H0), Hr[:, :hz]], 1), 1)
            dd = (Hr[:, :hz] / pk[:, 1:] - 1).min(1)
            dd_after = (Hr[:, 59:hz] / pk[:, 60:hz + 1] - 1).min(1) if hz > 60 else np.zeros(len(H))
            rows.append(dict(シナリオ=scen, 案=lab, 年=hz // 12, 一億以上=(H >= 1e8).mean(), 平均=H.mean(), 中央値=np.median(H),
                             悪いほう10=np.percentile(H, 10), 悪いほう5=np.percentile(H, 5), 良いほう10=np.percentile(H, 90),
                             一億5千以上=(H >= 1.5e8).mean(), 二億以上=(H >= 2e8).mean(), 元本割れ=(H < Q.H0).mean(),
                             途中30超=(dd <= -0.3).mean(), 途中50超=(dd <= -0.5).mean(), 五年後に30超下落=(dd_after <= -0.3).mean()))
d = pd.DataFrame(rows); d.to_csv("out_cmp/release_D2.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 250)
for sc in ("基本", "ネガ寄せ", "直近"):
    x = d[(d.シナリオ == sc) & (d.年 > 5)].copy()
    for c in ("平均", "中央値", "悪いほう10", "悪いほう5", "良いほう10"): x[c] = (x[c] / 1e4).round(0)
    print("---", sc); print(x.drop(columns="シナリオ").round(4).to_string(index=False))
