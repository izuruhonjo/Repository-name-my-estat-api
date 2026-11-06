import sys, json; sys.path.insert(0,'.')
import numpy as np, pandas as pd, s2engine as E, hh
b=json.load(open("out_1106/base.json"))
# 基準シナリオ：QQQ 11/6 +1.01%（時間外の水準）→ 基準価額16,020円★
W0=19590431+19590432; D0=b["dc_f"]+b["dc_d"]; N0=355464*2
mkt=hh.load_all("data"); A=hh.asset_returns(mkt); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
s2=E.simulate(mkt,assets,judg,E.Cfg())
D1="D1 DC④（○先進国株／×元本確保）"
navs={D1:hh.run_dc(mkt,A,judg,hh.DC_RULES[D1])[0]}
T=hh.build_month_table(s2["nav"],s2["states"],navs,A,rate_daily=mkt["rate"])
neg=E.negative_tilt_weights(T["S2"])
rows=[]
for lbl,kw in [("A 現状（目標ルールなし）",dict(goal=False)),("B 目標ルールあり",{}),("E 目標ルール（TQQQなし）",dict(behind=2.0))]:
    kw=dict(kw,dc_col=D1,cS2=0,cN=50_000,W0=W0,D0=D0,N0=N0)
    r=hh.hh_mc(T,**kw); rn=hh.hh_mc(T,weights=neg,**kw); rr=hh.hh_mc(T,start_idx=np.arange(0,len(T)-60),**kw)
    r7=hh.hh_mc(T,months=84,**kw); r1=hh.hh_mc(T,months=12,target=9.99e15,**kw)
    rows.append(dict(案=lbl,五年1億=r["p_hit"],ネガ寄せ=rn["p_hit"],歴史5年窓=rr["p_hit"],七年1億=r7["p_hit"],
        五年中央値=r["median"]/1e4,五年下位10=r["p10"]/1e4,五年上位10=r["p90"]/1e4,途中DD30超=r["p_dd30"],途中DD50超=r["p_dd50"],
        一年後中央値=r1["median"]/1e4,一年後下位10=r1["p10"]/1e4,一年後上位10=r1["p90"]/1e4))
df=pd.DataFrame(rows); df.to_csv("out_1106/household_mc_1106.csv",index=False)
pd.set_option("display.width",250); print(f"起点 S2 {W0/1e4:,.1f}万 DC {D0/1e4:,.1f}万 NISA {N0/1e4:,.1f}万 計 {(W0+D0+N0)/1e4:,.1f}万")
print(df.round(3).to_string(index=False))
H0=W0+D0+N0; print("5年1億に必要な年率",f"{(1e8/H0)**(1/5)-1:.2%}")
# 戦略指標（正典再構築エンジン、日次NAV）
nav=s2["nav"]; d=nav.pct_change().dropna(); yrs=(nav.index[-1]-nav.index[0]).days/365.25
cagr=(nav.iloc[-1]/nav.iloc[0])**(1/yrs)-1; vol=d.std()*np.sqrt(252); dd=(nav/nav.cummax()-1)
down=d[d<0].std()*np.sqrt(252); m=nav.resample("ME").last().pct_change().dropna()
yr=nav.resample("YE").last().pct_change().dropna()
ind=dict(期間=f"{nav.index[0].date()}〜{nav.index[-1].date()}",年率=cagr,年率ボラ=vol,シャープ_rf0=cagr/vol,ソルティノ=cagr/down,
  最大下落=dd.min(),カルマー=cagr/abs(dd.min()),最悪年=yr.min(),最良年=yr.max(),プラスの年=f"{(yr>0).sum()}/{len(yr)}",
  月次勝率=(m>0).mean(),最悪月=m.min(),最良月=m.max(),VaR95月=m.quantile(0.05),CVaR95月=m[m<=m.quantile(0.05)].mean(),
  直近5年年率=(nav.iloc[-1]/nav[nav.index<=nav.index[-1]-pd.DateOffset(years=5)].iloc[-1])**(1/5)-1,
  直近1年=nav.iloc[-1]/nav[nav.index<=nav.index[-1]-pd.DateOffset(years=1)].iloc[-1]-1)
json.dump({k:(float(v) if not isinstance(v,str) else v) for k,v in ind.items()},open("out_1106/s2_indicators.json","w"),ensure_ascii=False,indent=1)
for k,v in ind.items(): print(k, v if isinstance(v,str) else round(float(v),4))
