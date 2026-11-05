import sys, math; sys.path.insert(0,'.')
import pandas as pd, numpy as np, s2engine as E
mkt=E.load_market("data"); assets=E.build_assets(mkt); judg=E.judge_states(mkt)
s2=E.simulate(mkt,assets,judg,E.Cfg()); mr=E.monthly_returns(s2["nav"])
E.TAX=0.0; mpre=E.monthly_returns(E.simulate(mkt,assets,judg,E.Cfg())["nav"]); E.TAX=0.20315
u=(mr/2).values; tau=((mpre-mr)/2).values   # 1倍あたりの税引後リターンと、税で失っている分
def mc(behind=2.0, ahead=1.2, reached=0.5, nisa_per_year=0.0, nisa_lev=1.0, contrib=0, n=20000, seed=42, weights=None, months=60,
       W0=39_700_000, other0=9_650_000+77_500*60*0.5, other_g=0.06, target=1e8, rate=0.035, lev_cost=0.004, goal=True):
    rng=np.random.default_rng(seed); T=len(u); block=12; starts=np.arange(0,T-block+1)
    p=None if weights is None else np.asarray(weights)[:len(starts)]/np.asarray(weights)[:len(starts)].sum()
    nb=math.ceil(months/block); pick=rng.choice(starts,size=(n,nb),p=p)
    U=np.concatenate([u[pick[:,k][:,None]+np.arange(block)] for k in range(nb)],axis=1)[:,:months]
    TAU=np.concatenate([tau[pick[:,k][:,None]+np.arange(block)] for k in range(nb)],axis=1)[:,:months]
    W=np.full(n,float(W0)); peak=W.copy(); hit=np.zeros(n,bool); mindd=np.zeros(n); other=np.full(n,float(other0)); nisa=np.zeros(n)
    for t in range(months):
        if t%12==0 and t>0: nisa=np.minimum(nisa+nisa_per_year, W)   # 毎年1月にNISAへ移管（上限：資産）
        s=np.where(W>0, nisa/W, 0.0)
        req=W0*(target/W0)**(t/months); F=W/req
        L=np.full(n,2.0)
        if goal:
            L=np.where(F<0.85,behind,np.where(F>1.15,ahead,2.0)); L=np.where(W+other>=target,reached,L)
        # NISA部分はレバ nisa_lev、課税部分は L（ただし全体の平均レバ）
        Lt=(1-s)*L+s*nisa_lev
        r=Lt*U[:,t]-np.maximum(Lt-1,0)*(rate+lev_cost)/12 + s*nisa_lev*TAU[:,t]
        W=W*(1+r)+contrib; nisa=nisa*(1+nisa_lev*U[:,t]+nisa_lev*TAU[:,t])
        other*=1+other_g/12; peak=np.maximum(peak,W); mindd=np.minimum(mindd,W/peak-1); hit|=(W+other)>=target
    return dict(p=hit.mean(),med=np.median(W+other),p10=np.percentile(W+other,10),dd30=(mindd<=-0.3).mean(),dd50=(mindd<=-0.5).mean())
def show(lbl,**kw):
    r=mc(**kw); print(f"{lbl:50s} P(1億)={r['p']:.3f} 中央値={r['med']/1e4:,.0f}万 下位10%={r['p10']/1e4:,.0f}万 P(DD30)={r['dd30']:.3f} P(DD50)={r['dd50']:.3f}")
show("S2 現状",goal=False)
show("①目標ルール（遅れ=2倍据え置き／先行1.2倍／到達0.5倍）")
show("②NISA移管 年720万（NISA側は1倍）",goal=False,nisa_per_year=7_200_000)
show("②' NISA移管 年360万（夫のみ）",goal=False,nisa_per_year=3_600_000)
show("①＋②",nisa_per_year=7_200_000)
show("①＋②＋積立+5万/月",nisa_per_year=7_200_000,contrib=50_000)
show("①＋②＋積立+10万/月",nisa_per_year=7_200_000,contrib=100_000)
show("①＋②' ＋積立+5万/月",nisa_per_year=3_600_000,contrib=50_000)
w=E.negative_tilt_weights(mr)
show("S2 現状・ネガ寄せ",goal=False,weights=w)
show("①＋②＋積立+5万・ネガ寄せ",nisa_per_year=7_200_000,contrib=50_000,weights=w)
show("参考：遅れたら2.6倍（Browne型）",behind=2.6,nisa_per_year=7_200_000,contrib=50_000)
show("参考：到達後も2倍のまま",reached=2.0,ahead=2.0,nisa_per_year=7_200_000,contrib=50_000)
print("---- 最終候補 ----")
show("G5-A：遅れ2.6倍／先行1.2倍／到達0.5倍＋積立+5万",behind=2.6,contrib=50_000)
show("G5-B：同上＋積立+10万",behind=2.6,contrib=100_000)
show("G5-A ネガ寄せ",behind=2.6,contrib=50_000,weights=w)
show("G5-A 直近2013年〜だけで抽出",behind=2.6,contrib=50_000,weights=np.where(mr.index>="2013-01-01",1.0,0.0))
show("参考：遅れ3.0倍",behind=3.0,contrib=50_000)
show("参考：遅れ2.3倍",behind=2.3,contrib=50_000)
show("参考：G5-Aで到達後も2倍のまま",behind=2.6,reached=2.0,contrib=50_000)
show("参考：G5-Aで先行時も2倍のまま",behind=2.6,ahead=2.0,contrib=50_000)
show("S2現状＋積立+5万（ルール変更なし）",goal=False,contrib=50_000)
