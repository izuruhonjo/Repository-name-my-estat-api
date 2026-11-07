import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, imp_common as C, hh, s2engine as E
w=C.World("data"); r=w.run(dict(keep_brake_on_switch=True))
_,T=C.household(w,r["nav"],r["states"]); neg=E.negative_tilt_weights(T["S2"])
H0=C.W0+C.D0+C.N0
kw=dict(dc_col=C.D1,cS2=0,cN=50_000,W0=C.W0,D0=C.D0,N0=C.N0)
rows=[]
for lbl,g in [("K0 目標なし",False),("K0 目標あり",True)]:
    for scen,extra in [("基本",{}),("ネガ寄せ",dict(weights=neg)),("直近2013-",None)]:
        for mo in (36,48,60,84):
            k=dict(kw,goal=g,months=mo)
            TT=T[T.index>="2013-01-01"] if extra is None else T
            ex={} if extra is None else extra
            p=hh.hh_mc(TT,return_paths=True,**{**k,**ex})
            H=p["H"]
            rows.append(dict(案=lbl,シナリオ=scen,月数=mo,途中で1億=p["hit"].mean(),満期で1億以上=(H>=1e8).mean(),
              満期で9000万以上=(H>=9e7).mean(),満期中央値=np.median(H)/1e4,満期下位10=np.percentile(H,10)/1e4,満期下位5=np.percentile(H,5)/1e4,
              元本割れ=(H<H0).mean(),途中30超下落=(p["mindd"]<=-0.30).mean(),途中40超下落=(p["mindd"]<=-0.40).mean(),途中50超下落=(p["mindd"]<=-0.50).mean()))
df=pd.DataFrame(rows); df.to_csv("out_imp/choose_goal_vs_nogoal.csv",index=False)
pd.set_option("display.width",250); pd.set_option("display.max_columns",30)
print("起点",round(H0/1e4,1),"万")
print(df[df.シナリオ=="基本"].round(4).to_string(index=False))
print(df[df.月数.isin([60,84])&(df.シナリオ!="基本")].round(4).to_string(index=False))
