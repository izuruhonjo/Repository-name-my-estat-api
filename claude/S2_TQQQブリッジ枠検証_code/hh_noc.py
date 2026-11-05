import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, s2engine as E, hh
mkt=hh.load_all("data"); A=hh.asset_returns(mkt); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
s2=E.simulate(mkt,assets,judg,E.Cfg())
D1="D1 DC④（○先進国株／×元本確保）"; D6="D6 ○NASDAQ100／×元本確保（品揃えにある場合）"; D8="D8 ○米国株S&P500／×元本確保（品揃えにある場合）"
navs={k:hh.run_dc(mkt,A,judg,hh.DC_RULES[k])[0] for k in [D1,D6,D8]}
T=hh.build_month_table(s2["nav"],s2["states"],navs,A,rate_daily=mkt["rate"])
neg=E.negative_tilt_weights(T["S2"])
rows=[]
for W0 in [39_700_000, 42_270_000]:
    def row(lbl,**kw):
        kw.setdefault("dc_col",D1); kw.setdefault("cS2",0); kw.setdefault("cN",50_000); kw["W0"]=W0
        r=hh.hh_mc(T,**kw); rn=hh.hh_mc(T,weights=neg,**kw); rr=hh.hh_mc(T,start_idx=np.arange(0,len(T)-60),**kw)
        r7=hh.hh_mc(T,months=84,**kw)
        rows.append(dict(S2起点=W0/1e4,案=lbl,一度でも1億=r["p_hit"],ネガ寄せ=rn["p_hit"],歴史5年窓=rr["p_hit"],七年以内=r7["p_hit"],
                         中央値=r["median"]/1e4,下位10=r["p10"]/1e4,上位10=r["p90"]/1e4,途中DD30=r["p_dd30"],途中DD50=r["p_dd50"],
                         S2中央=r["med_S2"]/1e4,DC中央=r["med_DC"]/1e4,NISA中央=r["med_NISA"]/1e4))
    row("A 現状（目標ルールなし・DC④）",goal=False)
    row("B 目標ルール・DC④")
    row("C 目標ルール・DCの○がS&P500",dc_col=D8)
    row("D 目標ルール・DCの○がNASDAQ100",dc_col=D6)
    row("E 目標ルール（TQQQなし）・DC④",behind=2.0)
    row("F 目標ルール（TQQQなし）・DCの○がNASDAQ100",behind=2.0,dc_col=D6)
df=pd.DataFrame(rows); df.to_csv("out_hh/no_s2_contrib.csv",index=False)
pd.set_option("display.width",260); print(df.round(3).to_string())
for W0 in [39_700_000,42_270_000]:
    H0=W0+9_000_000+650_000
    print(f"S2起点{W0/1e4:,.0f}万 世帯起点{H0/1e4:,.0f}万 必要月率{(1e8/H0)**(1/60)-1:.4%}  経路:",[f"{H0*(1e8/H0)**(t/60)/1e4:,.0f}" for t in (12,24,36,48,60)])
