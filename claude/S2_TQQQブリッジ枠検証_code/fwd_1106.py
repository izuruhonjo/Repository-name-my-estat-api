# 11/9約定の売却額推計と、実額起点の世帯MC（2026-11-06）
import sys, json; sys.path.insert(0,'.')
import numpy as np, pandas as pd
# --- 市場（Twelve Data 日足終値） ---
q4,q5=691.95001,647.049988; g4,g5,g6=4058.01809,4114.39555,4042.25272  # g6は11/6日中値
fx3,fx4,fx5,fx6=158.74058,158.48698,157.85067,157.81594
spy=(733/766.81-1); efa=(102.70/105.72-1)
# 検算：11/5基準価額(+4.24%実績)を同じ式で再現
chk=(1+(q4/685.28003-1)+(g4/3919.19994-1))*(fx4/fx3)-1
nav5=17080
nav6=nav5*(1+(q5/q4-1)+(g5/g4-1))*(fx5/fx4)
U={"夫":6338663,"妻":5889793}; Ukeep={"夫":6338664,"妻":5889793}
fang_u=40333; fang_nav5=94546
# FANG+：11/5米国。NYFANG未取得→QQQ比1.15倍★で近似
fang6=fang_nav5*(1+1.15*(q5/q4-1))*(fx5/fx4)
rows=[]
for rq in [-0.04,-0.02,0.0,0.0101,0.02,0.04]:
    nav9=nav6*(1+rq+(g6/g5-1))*(fx6/fx5)
    sell=sum(U.values())*nav9/1e4; keep=sum(Ukeep.values())*nav9/1e4
    fang9=fang6*(1+1.15*rq)*(fx6/fx5)
    rows.append(dict(QQQ_11月6日=f"{rq:+.2%}",QQQ終値=round(q5*(1+rq),2),基準価額11月9日=round(nav9),
        夫売却=round(U["夫"]*nav9/1e4),妻売却=round(U["妻"]*nav9/1e4),夫婦売却計=round(sell),
        夫婦残り投信=round(keep),NISA売却=round(fang_u*fang9/1e4),NISA残り=round(fang_u*fang9/1e4)))
sc=pd.DataFrame(rows); sc.to_csv("out_1106/proceeds_scenarios.csv",index=False)
print(f"検算 11/5基準価額 予測{chk:+.2%} 実績+4.24%")
print(f"11/6基準価額（今夜公表）推計 {nav6:,.0f}円（{nav6/nav5-1:+.2%}）")
pd.set_option("display.width",250); print(sc.to_string(index=False))
# DC 11/6基準価額推計
kok=0.75*spy+0.25*efa
dc_f=8163199*(1+kok)*(fx5/fx4); dc_d=937200*(1-0.05)
print(f"DC 外国株 {dc_f:,.0f}（MSCIコクサイ≈SPY75%+EFA25%={kok:+.2%}、円{fx5/fx4-1:+.2%}）国内株 {dc_d:,.0f}（−5%★）")
json.dump(dict(nav6=nav6,dc_f=dc_f,dc_d=dc_d,fang6=fang6),open("out_1106/base.json","w"))
