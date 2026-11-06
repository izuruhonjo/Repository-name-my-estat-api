"""DC・NISA（FANG+）にボラ・ブレーキを足した場合の検証"""
import sys, itertools, math; sys.path.insert(0,'.')
import numpy as np, pandas as pd, s2engine as E, hh, signals as SG
pd.set_option("display.width",250); pd.set_option("display.max_rows",200)
mkt=hh.load_all("data"); A=hh.asset_returns(mkt); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
s2=E.simulate(mkt,assets,judg,E.Cfg())
idx=mkt.index; i0=idx.searchsorted(pd.Timestamp("2000-04-01")); i1=idx.searchsorted(pd.Timestamp("2026-10-31"),side="right")
me=set(E.month_end_dates(idx))
vol_q=SG.realized_vol(mkt["qqq"]).values
own_px={"DEV":(1+A["DEV"]).cumprod(),"FANG":(1+A["FANG"]).cumprod()}
vol_own={k:SG.realized_vol(v).values for k,v in own_px.items()}
D1="D1 DC④（○先進国株／×元本確保）"
nav_d1,hold_d1,_=hh.run_dc(mkt,A,judg,hh.DC_RULES[D1])
hold=hold_d1.reindex(idx[i0:i1]).values

def sim(asset, safe, holding, vol, th, frac, sell_lag=1, restore_lag=1):
    """holding[i]: その日に本体が資産を持っているか。ブレーキ中は frac を safe に置く。"""
    ra=A[asset].values; rs=A[safe].values
    v=1.0; nav=np.zeros(i1-i0); braked=False; on_from=None; off_from=None; n_trig=0; days_b=0
    for i in range(i0,i1):
        k=i-i0
        if on_from is not None and i>=on_from: braked=True; on_from=None
        if off_from is not None and i>=off_from: braked=False; off_from=None
        h=holding[k]
        if h:
            w=(1-frac) if braked else 1.0
            r=w*ra[i]+(1-w)*rs[i]; days_b+=braked
        else:
            r=rs[i] if holding is not None else 0.0
            braked=False; on_from=None
        v*=1+r; nav[k]=v
        x=vol[i]
        if h and not braked and on_from is None and not np.isnan(x) and x>=th:
            on_from=i+sell_lag; n_trig+=1
        if idx[i] in me and braked and not np.isnan(x) and x<th:
            off_from=i+restore_lag
    return pd.Series(nav,index=idx[i0:i1]), n_trig, days_b/(i1-i0)

# DC：本体が DEV を持つ日だけブレーキ対象。待機は元本確保。DCは売買に日数がかかるので sell_lag=2, restore_lag=5
dc_hold=np.array([h=="DEV" for h in hold])
# DCの「持ち物が無い日」は元本確保の利回り（CASH/PRINをまとめて PRIN扱い）
def dc_sim(sig,th,frac):
    vol = vol_q if sig=="QQQ" else vol_own["DEV"]
    nav,n,share=sim("DEV","PRIN",dc_hold,vol,th,frac,sell_lag=2,restore_lag=5)
    return nav,n,share
nisa_hold=np.ones(i1-i0,bool)
def ni_sim(sig,th,frac):
    vol = vol_q if sig=="QQQ" else vol_own["FANG"]
    return sim("FANG","CASH",nisa_hold,vol,th,frac,sell_lag=1,restore_lag=1)

TR,TE=("2000-04-01","2012-12-31"),("2013-01-01","2026-10-31")
sub=lambda s,a,b:s[(s.index>=a)&(s.index<=b)]
def mets(nav):
    m,mt,me_=E.metrics(nav),E.metrics(sub(nav,*TR)),E.metrics(sub(nav,*TE))
    return dict(年率=m["CAGR"],最大下落=m["MaxDD"],最悪年=m["WorstYear"],前半年率=mt["CAGR"],後半年率=me_["CAGR"],シャープ=m["Sharpe"])
# 基準（ブレーキなし）
base_dc,_,_=dc_sim("QQQ",9.9,0.5); base_ni,_,_=ni_sim("QQQ",9.9,0.5)
rows=[]; navs={}
rows.append(dict(口座="DC",案="ブレーキなし（DC④）",発動回数=0,ブレーキ中の日=0,**mets(base_dc))); navs[("DC","none")]=base_dc
rows.append(dict(口座="NISA",案="ブレーキなし（持ちっぱなし）",発動回数=0,ブレーキ中の日=0,**mets(base_ni))); navs[("NISA","none")]=base_ni
grid_q=[0.25,0.30,0.35,0.40]
for acct,fn,own_th in [("DC",dc_sim,[0.20,0.25,0.30]),("NISA",ni_sim,[0.35,0.40,0.45,0.50])]:
    for sig,ths in [("QQQ",grid_q),("自分",own_th)]:
        for th,frac in itertools.product(ths,[0.5,1.0]):
            nav,n,share=fn(sig,th,frac)
            lbl=f"{sig}ボラ{int(th*100)}%で{'半分' if frac==0.5 else '全部'}"
            rows.append(dict(口座=acct,案=lbl,発動回数=n,ブレーキ中の日=share,**mets(nav))); navs[(acct,lbl)]=nav
df=pd.DataFrame(rows)
b=df.groupby("口座").first()
df["年率差"]=df.apply(lambda r:r["年率"]-b.loc[r["口座"],"年率"],axis=1)
df["下落差"]=df.apply(lambda r:r["最大下落"]-b.loc[r["口座"],"最大下落"],axis=1)
df["前半差"]=df.apply(lambda r:r["前半年率"]-b.loc[r["口座"],"前半年率"],axis=1)
df["後半差"]=df.apply(lambda r:r["後半年率"]-b.loc[r["口座"],"後半年率"],axis=1)
df.to_csv("out_hh/volbrake_dc_nisa.csv",index=False)
print(df[["口座","案","発動回数","ブレーキ中の日","年率","年率差","最大下落","下落差","前半差","後半差","最悪年","シャープ"]].round(4).to_string())
# FNGS実データ期間（2019-11〜）だけ
r0=A.index[A["FANG_real"]].min()
print("\n== FANG+実データ期間", r0.date(),"〜 ==")
for lbl in ["ブレーキなし（持ちっぱなし）","QQQボラ30%で半分","QQQボラ30%で全部","自分ボラ40%で半分"]:
    nv=navs[("NISA","none" if "なし" in lbl else lbl)]; nv=nv[nv.index>=r0]; m=E.metrics(nv)
    print(f"{lbl:22s} 年率 {m['CAGR']:.4f} 最大下落 {m['MaxDD']:.4f}")
# 世帯MC：DC・NISAにS2と同じルール（QQQボラ30%で半分）を入れた場合 ほか
navs_mc={"DCなし":navs[("DC","none")],"DC_Q30半":navs[("DC","QQQボラ30%で半分")],"DC_best":None}
dc_rows=df[(df.口座=="DC")&(df.案!="ブレーキなし（DC④）")]; best_dc=dc_rows.sort_values("年率差",ascending=False).iloc[0]["案"]
ni_rows=df[(df.口座=="NISA")&(~df.案.str.contains("なし"))]; best_ni=ni_rows.sort_values("年率差",ascending=False).iloc[0]["案"]
cols={"DC0":navs[("DC","none")],"DC1":navs[("DC","QQQボラ30%で半分")],"DCb":navs[("DC",best_dc)],
      "N0":navs[("NISA","none")],"N1":navs[("NISA","QQQボラ30%で半分")],"Nb":navs[("NISA",best_ni)]}
T=hh.build_month_table(s2["nav"],s2["states"],cols,A,rate_daily=mkt["rate"])
neg=E.negative_tilt_weights(T["S2"]); roll=np.arange(0,len(T)-60)
print("\n最良DC案:",best_dc," 最良NISA案:",best_ni)
print("\n== 世帯MC（目標ルール＋DC④、追加積立なし、S2起点3,970万） ==")
for lbl,dc,ni in [("ブレーキはS2だけ（今）","DC0","N0"),("DCにも（QQQ30%・半分）","DC1","N0"),("NISAにも（QQQ30%・半分）","DC0","N1"),("両方に（QQQ30%・半分）","DC1","N1"),
                  (f"DC最良案（{best_dc}）","DCb","N0"),(f"NISA最良案（{best_ni}）","DC0","Nb")]:
    kw=dict(dc_col=dc,nisa_col=ni,cS2=0,cN=50_000)
    r=hh.hh_mc(T,**kw); rn=hh.hh_mc(T,weights=neg,**kw); rr=hh.hh_mc(T,start_idx=roll,**kw)
    print(f"{lbl:34s} 1億={r['p_hit']:.3f} ネガ={rn['p_hit']:.3f} 歴史窓={rr['p_hit']:.3f} 中央値={r['median']/1e4:,.0f}万 下位10%={r['p10']/1e4:,.0f}万 DD30={r['p_dd30']:.3f} DC中央={r['med_DC']/1e4:,.0f} NISA中央={r['med_NISA']/1e4:,.0f}")
