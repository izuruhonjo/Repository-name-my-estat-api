import sys, itertools; sys.path.insert(0,'.')
import pandas as pd, numpy as np, g5, s2engine as E
pd.set_option("display.width",250); pd.set_option("display.max_rows",200)
mkt=g5.load("data"); R=g5.jpy_returns(mkt)
print("JP source:",g5.ASSETS["JP"])
R=R[[c for c in R.columns if R[c].notna().sum()>1000]]; print("assets",list(R.columns))
UNI={"全6":list(R.columns),"債券なし":[c for c in R.columns if c!="TLT"],"QQQ+金+半導体":["QQQ","GOLD","SMH"],"QQQ+金":["QQQ","GOLD"],"QQQ+金+日本株":["QQQ","GOLD","JP"]}
rows=[]
for (un,cols),wt,vt,lm in itertools.product(UNI.items(),["inv","eq","mom"],[0.20,0.25,0.30],[1.5,2.0]):
    nav,W,tx=g5.backtest(mkt,R[cols],vol_target=vt,lmax=lm,weighting=wt)
    m=E.metrics(nav); rows.append(dict(universe=un,weighting=wt,vol_target=vt,lmax=lm,CAGR=m["CAGR"],MaxDD=m["MaxDD"],Worst=m["WorstYear"],Min5y=m["Min5yCAGR"],Sharpe=m["Sharpe"],Vol=m["Vol"],avgL=W.sum(axis=1).mean()))
df=pd.DataFrame(rows).sort_values("CAGR",ascending=False); df.to_csv("out/g5_grid.csv",index=False)
print(df.round(3).head(30).to_string()); print("...worst"); print(df.round(3).tail(5).to_string())
