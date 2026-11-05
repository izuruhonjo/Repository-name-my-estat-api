import sys; sys.path.insert(0,'.')
import pandas as pd, numpy as np, s2engine as E, g5
mkt=E.load_market("data"); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
s2=E.simulate(mkt,assets,judg,E.Cfg()); mr=E.monthly_returns(s2["nav"])
E.TAX=0.0; s2pre=E.simulate(mkt,assets,judg,E.Cfg()); E.TAX=0.20315
mpre=E.monthly_returns(s2pre["nav"])
print("S2 after-tax CAGR",round(E.metrics(s2["nav"])["CAGR"],4),"pre-tax",round(E.metrics(s2pre["nav"])["CAGR"],4))
# 1x版（押し目のN1と同じ）：S2のリターンの半分を近似。レバ2＝S2そのもの
unlev = mr/2
W0=39_700_000; other0=9_650_000; contrib_other=77_500   # DC900+NISA65、DC2.75万+NISA5万/月
def run(label, mr_u, lmax=2.0, goal_rule=False, contrib=0, nisa_share=0.0, floor_dd=0.99, **kw):
    # nisa_share: 税引前と税引後の月次リターンの差をどれだけ取り戻すか（NISA移管の近似）
    r = (mr_u + (mpre/2 - mr/2)*nisa_share) if nisa_share>0 else mr_u
    res=g5.mc_goal(r, W0=W0, months=60, lmax=lmax, goal_rule=goal_rule, floor_dd=floor_dd, contrib=contrib, other0=other0, other_g=0.06, rate=0.035, lev_cost=0.004, **kw)
    # otherの積立は other0 に5年分の積立の現在価値相当を足して近似
    print(f"{label:48s} P(1億)={res['p_hit']:.3f}  中央値={res['median']/1e4:,.0f}万  下位10%={res['p10']/1e4:,.0f}万  P(DD30)={res['p_dd30']:.3f} P(DD50)={res['p_dd50']:.3f}")
    return res
g5.mc_goal.__defaults__  # noop
# other の積立を other0 に織り込む（5年分 = 77,500×60 = 465万、成長込みで約540万 → 半分を期初に足す近似）
other0 += 77_500*60*0.5
run("S2 現状（口座＋DC＋NISA）", unlev, lmax=2.0)
run("S2＋目標到達ルール（先行で1.2倍・到達後0.5倍）", unlev, lmax=2.0, goal_rule=True)
run("S2＋NISA移管（税の6割を取り戻す）", unlev, lmax=2.0, nisa_share=0.6)
run("S2＋目標ルール＋NISA移管", unlev, lmax=2.0, goal_rule=True, nisa_share=0.6)
run("S2＋目標ルール＋NISA移管＋積立+5万/月", unlev, lmax=2.0, goal_rule=True, nisa_share=0.6, contrib=50_000)
run("S2＋目標ルール＋NISA移管＋積立+10万/月", unlev, lmax=2.0, goal_rule=True, nisa_share=0.6, contrib=100_000)
run("S2 常時2.5倍（参考・危険）", unlev, lmax=2.5)
run("S2 常時3倍（参考・危険）", unlev, lmax=3.0)
run("S2 1.5倍（守り）", unlev, lmax=1.5)
# ネガ寄せ
w=E.negative_tilt_weights(mr)
run("S2 現状・ネガ寄せ", unlev, lmax=2.0, weights=w)
run("S2＋目標ルール＋NISA移管・ネガ寄せ", unlev, lmax=2.0, goal_rule=True, nisa_share=0.6, weights=w)
# BTC 5%スリーブ（2017-09〜）
btc=mkt["btc"]*mkt["fx"]; rb=btc.pct_change().fillna(0)
sma200=btc.rolling(200).mean()
me=E.month_end_dates(mkt.index); on=(btc.loc[me]>sma200.loc[me]).reindex(mkt.index).ffill().fillna(False)
nav=s2["nav"]; r_s2=nav.pct_change().fillna(0)
mix=(0.95*r_s2+0.05*rb.where(on.shift(1).fillna(False),0.0))
sub=lambda s:s[(s.index>="2017-09-01")]
n0=(1+sub(r_s2)).cumprod(); n1=(1+sub(mix)).cumprod()
m0,m1=E.metrics(n0),E.metrics(n1); print(f"2017-09〜2026-10  S2: CAGR {m0['CAGR']:.3f} MaxDD {m0['MaxDD']:.3f} | S2+BTC5%(200日線ゲート): CAGR {m1['CAGR']:.3f} MaxDD {m1['MaxDD']:.3f}")
