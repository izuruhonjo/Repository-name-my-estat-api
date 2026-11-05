import sys, itertools, json; sys.path.insert(0,'.')
import pandas as pd, numpy as np, s2engine as E, signals as SG
mkt=E.load_market("data"); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
ohlc=pd.read_csv("data/QQQ.csv",parse_dates=["date"]).set_index("date")[["high","low"]].reindex(mkt.index).ffill()
SIG=SG.build_signals(mkt,ohlc)
run=lambda cfg: E.simulate(mkt,assets,judg,cfg)
base=run(E.Cfg()); mb=E.metrics(base["nav"])
STARTS=["2000-04-01","2002-10-01","2007-10-01","2013-01-01"]; COSTS=[0,0.0025,0.005]; LAGS=[1,2,3,5]
g_s2=pd.DataFrame([dict(start=s,cost=c,lag=l,CAGR=E.metrics(run(E.Cfg(start=s,slippage=c,exec_lag=l))["nav"])["CAGR"]) for s,c,l in itertools.product(STARTS,COSTS,LAGS)])
def grid(bfn):
    g=pd.DataFrame([dict(start=s,cost=c,lag=l,**{k:v for k,v in E.metrics(run(E.Cfg(start=s,slippage=c,exec_lag=l,bridge=bfn()))["nav"]).items() if k in("CAGR","MaxDD")}) for s,c,l in itertools.product(STARTS,COSTS,LAGS)])
    g=g.merge(g_s2,on=["start","cost","lag"],suffixes=("","_S2")); return int((g.CAGR>g.CAGR_S2).sum()), g.MaxDD.min(), (g.CAGR-g.CAGR_S2).mean()
cands={
 "Z0即時/TQQQ/30%/損切35": lambda: E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.3,stop_loss=0.35,signal=SIG["Z0_immediate"]),
 "Z0即時/SOXL/30%/損切15": lambda: E.BridgeCfg(enabled=True,asset="SOXL",budget_pct=0.3,stop_loss=0.15,signal=SIG["Z0_immediate"]),
 "B2/TQQQ/30%/損切35": lambda: E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.3,stop_loss=0.35,signal=SIG["B2_rv_peak>50_fall1/2"]),
 "E3/TQQQ/30%/損切35": lambda: E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.3,stop_loss=0.35,signal=SIG["E3_rv_cross_down25"]),
 "回復レバ/TQQQ/20%/3ヶ月": lambda: E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.2,stop_loss=0.25,recovery_months=3),
 "回復レバ/TQQQ/20%/6ヶ月": lambda: E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.2,stop_loss=0.25,recovery_months=6),
 "回復レバ/TQQQ/30%/6ヶ月": lambda: E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.3,stop_loss=0.25,recovery_months=6),
 "回復レバ/TQQQ/20%/12ヶ月": lambda: E.BridgeCfg(enabled=True,asset="TQQQ",budget_pct=0.2,stop_loss=0.25,recovery_months=12),
}
rows=[]; episodes={}
for k,fn in cands.items():
    r=run(E.Cfg(bridge=fn())); m=E.metrics(r["nav"]); w,wdd,md=grid(fn)
    mr=E.monthly_returns(r["nav"]); mc7=E.monte_carlo(mr,7); mc5=E.monte_carlo(mr,5)
    rows.append(dict(案=k,CAGR=m["CAGR"],dCAGR=m["CAGR"]-mb["CAGR"],MaxDD=m["MaxDD"],WorstYear=m["WorstYear"],wins48=w,worstDD48=wdd,mean_dCAGR48=md,
                     MC7_p1億=mc7["p_hit_target"],MC7_pDD30=mc7["p_dd_over"],MC5_p1億=mc5["p_hit_target"],MC5_pDD30=mc5["p_dd_over"],n_bridge=len([x for x in r["bridge_log"] if x[1]=="BUY"])))
    episodes[k]=r["bridge_log"]
mr=E.monthly_returns(base["nav"]); mc7=E.monte_carlo(mr,7); mc5=E.monte_carlo(mr,5)
rows.insert(0,dict(案="S2（このエンジン）",CAGR=mb["CAGR"],dCAGR=0,MaxDD=mb["MaxDD"],WorstYear=mb["WorstYear"],wins48=None,worstDD48=None,mean_dCAGR48=None,MC7_p1億=mc7["p_hit_target"],MC7_pDD30=mc7["p_dd_over"],MC5_p1億=mc5["p_hit_target"],MC5_pDD30=mc5["p_dd_over"],n_bridge=0))
df=pd.DataFrame(rows); df.to_csv("out/supplementary.csv",index=False)
pd.set_option("display.width",250); print(df.round(4).to_string())
# エピソード別損益（主要2案）
for k in ["Z0即時/TQQQ/30%/損切35","B2/TQQQ/30%/損切35","回復レバ/TQQQ/20%/6ヶ月"]:
    print("\n==",k); bl=pd.DataFrame(episodes[k],columns=["date","kind","amount","price","pnl"]); print(bl.round(0).to_string())
    bl.to_csv(f"out/bridge_log_{k.replace('/','_')}.csv",index=False)
