import sys, itertools; sys.path.insert(0,'.')
import pandas as pd, numpy as np, s2engine as E, signals as SG
pd.set_option("display.width",250)
mkt=E.load_market("data"); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
run=lambda cfg: E.simulate(mkt,assets,judg,cfg)
base=run(E.Cfg()); mb=E.metrics(base["nav"])
rv=SG.realized_vol(mkt["qqq"])
def e3(lo=0.25, prior=0.35, look=60):
    return ((rv<lo)&(rv.shift(1)>=lo)&(rv.rolling(look).max()>=prior)).fillna(False)
# 1) パラメータ面の滑らかさ
rows=[]
for lo,prior in itertools.product([0.20,0.22,0.25,0.28,0.30],[0.30,0.35,0.40,0.45]):
    if prior<=lo: continue
    for sl in [0.25,0.35]:
        m=E.metrics(run(E.Cfg(bridge=E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.3,stop_loss=sl,signal=e3(lo,prior))))["nav"])
        rows.append(dict(lo=lo,prior=prior,stop=sl,dCAGR=m["CAGR"]-mb["CAGR"],MaxDD=m["MaxDD"]))
df=pd.DataFrame(rows); df.to_csv("out/e3_param_surface.csv",index=False)
print("== E3 パラメータ面 (dCAGR, pt) ==")
print(df.pivot_table(index=["lo","prior"],columns="stop",values="dCAGR").round(4).to_string())
print("負の組合せ:",(df.dCAGR<0).sum(),"/",len(df))
# 2) 損切り・枠の感度（lo .25 / prior .35）
rows=[]
for bp in [0.1,0.2,0.3,0.4,0.5]:
    for sl in [0.15,0.25,0.35,0.45,0.99]:
        r=run(E.Cfg(bridge=E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=bp,stop_loss=sl,signal=e3())))
        m=E.metrics(r["nav"]); mc=E.monte_carlo(E.monthly_returns(r["nav"]),7,n_paths=5000)
        rows.append(dict(budget=bp,stop=sl,dCAGR=m["CAGR"]-mb["CAGR"],MaxDD=m["MaxDD"],WorstYear=m["WorstYear"],MC7_pDD30=mc["p_dd_over"],MC7_p1億=mc["p_hit_target"]))
df2=pd.DataFrame(rows); df2.to_csv("out/e3_budget_stop.csv",index=False); print("\n== 枠×損切り =="); print(df2.round(4).to_string())
# 3) S2の48通りの最悪MaxDD
STARTS=["2000-04-01","2002-10-01","2007-10-01","2013-01-01"]; COSTS=[0,0.0025,0.005]; LAGS=[1,2,3,5]
g=[E.metrics(run(E.Cfg(start=s,slippage=c,exec_lag=l))["nav"])["MaxDD"] for s,c,l in itertools.product(STARTS,COSTS,LAGS)]
print("\nS2 48通り 最悪MaxDD:",round(min(g),4))
# 4) エピソード別ログ（E3/TQQQ/30%/損切35）
r=run(E.Cfg(bridge=E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.3,stop_loss=0.35,signal=e3())))
bl=pd.DataFrame(r["bridge_log"],columns=["date","kind","amount","price","pnl"]); bl.to_csv("out/finalist_bridge_log.csv",index=False)
print("\n== E3/TQQQ/30%/損切35 売買 =="); print(bl.to_string())
# 年別 S2 vs E3
y1=r["nav"].resample("YE").last().pct_change(); y0=base["nav"].resample("YE").last().pct_change()
print(pd.DataFrame({"S2":y0,"E3":y1,"diff":y1-y0}).dropna().round(4).to_string())
r["nav"].to_csv("out/finalist_nav.csv")
# シグナル発生日（×中以外も含めて全部）
print("\nE3発生日(全期間):",[d.strftime("%Y-%m-%d") for d in e3().index[e3().values] if d>=pd.Timestamp("2000-04-01")])
