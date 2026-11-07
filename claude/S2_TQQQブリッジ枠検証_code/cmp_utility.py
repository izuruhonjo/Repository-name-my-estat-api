"""S2（A0）とD2（到達＝換金後）の5年末資産を、効用（CRRA）の確実性等価と、1億の閾値の損益分岐で比べる（専門家会議の材料）"""
import numpy as np
a = np.load("out_cmp/paths_A0.npz")["H60"] / 1e4; d = np.load("out_cmp/paths_D2_RL.npz")["H60"] / 1e4
ce = lambda x, g: np.exp(np.mean(np.log(x))) if g == 1 else (np.mean(x ** (1 - g))) ** (1 / (1 - g))
for g in (1, 2, 3, 5, 8, 12, 20):
    print(f"γ={g}  S2 {ce(a, g):,.0f}万  D2 {ce(d, g):,.0f}万")
win = (a < 1e4) & (d >= 1e4); gain = (d >= 1e4).mean() - (a >= 1e4).mean(); cost = (a - d).mean()
print(f"D2だけ1億 {win.mean():.2%}（S2中央値{np.median(a[win]):,.0f}万→D2 {np.median(d[win]):,.0f}万）、確率差{gain:.2%}、平均差{cost:,.0f}万、分岐点{cost / gain:,.0f}万")
