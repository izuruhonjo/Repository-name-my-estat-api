"""DCの対案（世帯MC・新しい物差し、S2はK0のまま＝A0）。出力 out_cmp/dc_alt.csv"""
import sys; sys.path.insert(0, ".")
import numpy as np, pandas as pd, cmp_common as Q, hh, s2x as X
w = Q.World2("data"); T, S = Q.build_all(w)
rows = []
for name in hh.DC_RULES:
    nav = hh.run_dc(w.mkt, w.A, w.judg["base"], hh.DC_RULES[name])[0]
    m = X.indicators(nav)
    T2 = T.copy(); T2[Q.D1] = hh.monthly(nav).reindex(T.index).values
    r = {"DCの規則": name, "DC単体の年率": m["CAGR"], "DC単体の最大下落": m["MaxDD"]}
    for scen in ("基本", "ネガ寄せ", "直近"):
        M = Q.draw_months(len(T), 100_000, 84, seed=42, **Q.scen_kw(T, scen))
        p = Q.household_mc(T2, S, Q.CANDS["A0"], months=84, M=M)
        s5, s7 = Q.summarize(p, 60), Q.summarize(p, 84)
        r[f"{scen}5年1億"] = s5["1億以上"]; r[f"{scen}7年1億"] = s7["1億以上"]
        if scen == "基本":
            r.update({"5年平均": (p["H60"]).mean(), "5年中央値": s5["中央値"], "5年悪いほう10%": s5["悪いほう10%"], "元本割れ": s5["元本割れ"], "途中30超": s5["途中30超"], "途中50超": s5["途中50超"], "7年平均": p["H"].mean()})
    rows.append(r)
d = pd.DataFrame(rows); d.to_csv("out_cmp/dc_alt.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
for c in ("5年平均", "5年中央値", "5年悪いほう10%", "7年平均"): d[c] = (d[c] / 1e4).round(0)
print(d.round(4).to_string(index=False))
