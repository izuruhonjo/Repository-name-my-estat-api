import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, s2engine as E, hh
mkt=hh.load_all("data"); A=hh.asset_returns(mkt); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
s2=E.simulate(mkt,assets,judg,E.Cfg())
D1="D1 DC④（○先進国株／×元本確保）"; D6="D6 ○NASDAQ100／×元本確保（品揃えにある場合）"
def table(A_, cash_days=5):
    navs={}
    for nm in [D1,D6]:
        nv,_,_=hh.run_dc(mkt,A_,judg,hh.DC_RULES[nm],cash_days=cash_days); navs[nm]=nv
    return hh.build_month_table(s2["nav"],s2["states"],navs,A_,rate_daily=mkt["rate"])
def p(T,**kw):
    r=hh.hh_mc(T,**kw); return f"{r['p_hit']:.3f}"
# ① FANG+ 2019年以前に +6%/年のアルファを仮定
A2=A.copy(); A2.loc[~A2["FANG_real"],"FANG"]+=0.06/252
T1=table(A); T2=table(A2)
print("FANG+の仮定        | NISA持ちっぱなし | ×月にS2→NISA | 毎年1月に枠埋め | S2積立→NISA")
for lbl,T in [("2019以前=NASDAQ100",T1),("2019以前=NASDAQ100+6%",T2)]:
    print(f"{lbl:22s}", p(T,dc_col=D1,cS2=50_000), p(T,dc_col=D1,cS2=50_000,nisa_from_s2_in_retreat=1.0), p(T,dc_col=D1,cS2=50_000,nisa_jan_fill=1.0), p(T,dc_col=D1,cS2=0,cN=100_000))
# ② DCスイッチングの待ち日数
for cd in [2,5,10]:
    T=table(A,cash_days=cd)
    m1=E.metrics(hh.run_dc(mkt,A,judg,hh.DC_RULES[D1],cash_days=cd)[0])
    print(f"DC待ち{cd:2d}営業日: DC④年率 {m1['CAGR']:.4f} 最大下落 {m1['MaxDD']:.4f} | 世帯P(1億) D1={p(T,dc_col=D1,cS2=50_000)} D6={p(T,dc_col=D6,cS2=50_000)}")
# ③ 目標ルールの閾値感度（0.80/0.90、1.10/1.20）
for lo,hi in [(0.80,1.15),(0.90,1.15),(0.85,1.10),(0.85,1.20)]:
    import inspect
    src=inspect.getsource(hh.hh_mc)
print("閾値感度は次のブロックで")
