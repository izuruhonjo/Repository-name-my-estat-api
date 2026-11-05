import sys; sys.path.insert(0,'.')
import numpy as np, pandas as pd, s2engine as E, hh
from openpyxl import Workbook
from openpyxl.styles import Font
mkt=hh.load_all("data"); A=hh.asset_returns(mkt); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
s2=E.simulate(mkt,assets,judg,E.Cfg())
D1="D1 DC④（○先進国株／×元本確保）"; D6="D6 ○NASDAQ100／×元本確保（品揃えにある場合）"; D8="D8 ○米国株S&P500／×元本確保（品揃えにある場合）"
navs={k:hh.run_dc(mkt,A,judg,hh.DC_RULES[k])[0] for k in [D1,D6,D8]}
T=hh.build_month_table(s2["nav"],s2["states"],navs,A,rate_daily=mkt["rate"])
neg=E.negative_tilt_weights(T["S2"]); roll=np.arange(0,len(T)-60)
rows=[]
def row(lbl,**kw):
    r=hh.hh_mc(T,**kw); rn=hh.hh_mc(T,weights=neg,**kw); rr=hh.hh_mc(T,start_idx=roll,**kw)
    rows.append(dict(案=lbl,一度でも1億=r["p_hit"],ネガ寄せ=rn["p_hit"],歴史5年窓=rr["p_hit"],中央値万=r["median"]/1e4,下位10万=r["p10"]/1e4,途中DD30=r["p_dd30"],途中DD50=r["p_dd50"],
                     S2中央万=r["med_S2"]/1e4,DC中央万=r["med_DC"]/1e4,NISA中央万=r["med_NISA"]/1e4))
row("① 現状（S2＋DC④＋NISA5万、積立追加なし）",dc_col=D1,goal=False,cS2=0)
row("② H5-基本：目標ルール＋DC④＋NISA月10万",dc_col=D1,cS2=0,cN=100_000)
row("③ H5-基本：目標ルール＋DC④＋S2月5万",dc_col=D1,cS2=50_000)
row("④ H5-推奨：目標ルール＋DC④＋S2月5万＋NISA月10万",dc_col=D1,cS2=50_000,cN=100_000)
row("⑤ ④でDCの○がS&P500",dc_col=D8,cS2=50_000,cN=100_000)
row("⑥ ④でDCの○がNASDAQ100",dc_col=D6,cS2=50_000,cN=100_000)
df=pd.DataFrame(rows); df.to_csv("out_hh/final_plans.csv",index=False)
pd.set_option("display.width",250); print(df.round(3).to_string())
# 世帯の必要経路
H0=39_700_000+9_000_000+650_000
print("\n必要経路（世帯）:", [f"{t}ヶ月 {H0*(1e8/H0)**(t/60)/1e4:,.0f}万" for t in (0,12,24,36,48,60)])
print("月あたり必要成長率:", round((1e8/H0)**(1/60)-1,5))
# ---- Excel突合：直近の5年窓（歴史そのまま）を数式で再計算 ----
k0=len(T)-60
kw=dict(dc_col=D1,cS2=50_000,cN=100_000)
P=hh.hh_mc(T,start_idx=[k0],return_paths=True,**kw)
sub=T.iloc[k0:k0+60]
wb=Workbook(); ws=wb.active; ws.title="世帯5年窓"
params=[("W0",39_700_000),("D0",9_000_000),("N0",650_000),("cS2",50_000),("cDC",27_500),("cN",100_000),("目標",1e8),("lo",0.85),("hi",1.15),("遅れL",2.5),("先行L",1.2),("到達L",0.5),("基本L",2.0),("TQQQ追加コスト",0.03)]
for i,(k,v) in enumerate(params,start=1):
    ws.cell(i,14,k); ws.cell(i,15,v)
# 参照: O1=W0 O2=D0 O3=N0 O4=cS2 O5=cDC O6=cN O7=目標 O8=lo O9=hi O10=遅れL O11=先行L O12=到達L O13=基本L O14=levcost
hdr=["月","S2月次","×フラグ","金利(年)","DC月次","NISA月次","世帯(月初)","必要経路","到達度F","濃さL","S2実効リターン","S2残高","DC残高","NISA残高","世帯(月末)"]
for j,h in enumerate(hdr,start=1):
    ws.cell(18,j,h).font=Font(bold=True)
H0c="($O$1+$O$2+$O$3)"
for t,(d,r) in enumerate(sub.iterrows()):
    R=19+t
    ws.cell(R,1,d.strftime("%Y-%m")); ws.cell(R,2,float(r["S2"])); ws.cell(R,3,float(r["RET"])); ws.cell(R,4,float(r["RATE"])); ws.cell(R,5,float(r[D1])); ws.cell(R,6,float(r["A_FANG"]))
    prevW = "$O$1" if t==0 else f"L{R-1}"; prevD="$O$2" if t==0 else f"M{R-1}"; prevN="$O$3" if t==0 else f"N{R-1}"
    ws.cell(R,7,f"={prevW}+{prevD}+{prevN}")
    ws.cell(R,8,f"={H0c}*($O$7/{H0c})^({t}/60)")
    ws.cell(R,9,f"=G{R}/H{R}")
    ws.cell(R,10,f"=IF(G{R}>=$O$7,$O$12,IF(I{R}<$O$8,$O$10,IF(I{R}>$O$9,$O$11,$O$13)))")
    ws.cell(R,11,f"=IF(C{R}>0.5,B{R},(J{R}/2)*B{R}-(MAX(J{R}-1,0)-J{R}/2)*D{R}/12-MAX(J{R}-2,0)*$O$14/12)")
    ws.cell(R,12,f"=({prevW}+$O$4)*(1+K{R})")
    ws.cell(R,13,f"=({prevD}+$O$5)*(1+E{R})")
    ws.cell(R,14,f"=({prevN}+$O$6)*(1+F{R})")
    ws.cell(R,15,f"=L{R}+M{R}+N{R}")
last=19+59
ws.cell(1,17,"最終 世帯(式)"); ws.cell(1,18,f"=O{last}")
ws.cell(2,17,"最終 世帯(Python)"); ws.cell(2,18,float(P["H"][0]))
ws.cell(3,17,"最終 S2(式/Py)"); ws.cell(3,18,f"=L{last}"); ws.cell(3,19,float(P["W"][0]))
ws.cell(4,17,"最終 DC(式/Py)"); ws.cell(4,18,f"=M{last}"); ws.cell(4,19,float(P["D"][0]))
ws.cell(5,17,"最終 NISA(式/Py)"); ws.cell(5,18,f"=N{last}"); ws.cell(5,19,float(P["N"][0]))
ws.cell(6,17,"一度でも1億(式)"); ws.cell(6,18,f"=IF(MAX(O19:O{last})>=$O$7,1,0)")
ws.cell(7,17,"一度でも1億(Py)"); ws.cell(7,18,int(P["hit"][0]))
ws.cell(8,17,"差(世帯)"); ws.cell(8,18,"=R1/R2-1")
wb.save("out_hh/H5_世帯Excel突合.xlsx"); print("saved; window",sub.index[0].date(),"→",sub.index[-1].date(), "Python final H", round(P['H'][0]))
