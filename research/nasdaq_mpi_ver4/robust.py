import sys; sys.path.insert(0,'.')
from mpi import *
daily=pd.read_pickle('data/daily.pkl')
m=monthly_bars(daily).loc[:'2026-10']; s=signals(m)
cost3,_=calibrate_cost(daily,'TQQQ',3)
C=Cfg(name='C',lev_cost=cost3,financing=True,one_er=0.0015,dividends=True,exec_lag=1,contrib_at_month_end=False,
      commission=0.00495,comm_cap_usd=22,slippage=0.0002,fx=True,jp_tax=True,div_tax=True,end='2026-10',infl_adj=False)
CM=replace(C,name='C-MOC',exec_lag=0,contrib_at_month_end=True)
out={}
# 1 開始年シフト(名目3万)
rows=[]
for st in ['1985-10','1990-01','1995-01','2000-01','2005-01','2010-01','2015-01','2020-01']:
    for lab,c in [('MPI(C 翌日)',C),('MPI(C-MOC)',CM),('QQQM積立',replace(C,strategy='dca1')),('TQQQ積立',replace(C,strategy='dca3'))]:
        r,h,t=run(daily,s,replace(c,start=st)); rows.append(dict(start=st,strat=lab,final=r['final_after_liq'],contrib=r['contrib'],irr=r['irr'],mdd=r['mdd_twr']))
out['start']=pd.DataFrame(rows)
# 2 パラメータ感応度 (C-MOC と C)
rows=[]
for mx in [0.1,0.15,0.2,0.25,0.3]:
    for mp in [(8,17,9),(10,22,7),(12,26,9),(14,30,11),(16,34,12)]:
        ss=signals(m,*mp,ps=(0.02,0.02,mx))
        for lab,c in [('C',C),('C-MOC',CM)]:
            r,h,t=run(daily,ss,replace(c,ps=(0.02,0.02,mx),macd=mp,start='1985-10'))
            rows.append(dict(psar_max=mx,macd=str(mp),cfg=lab,final=r['final_after_liq'],irr=r['irr'],mdd=r['mdd_twr'],trades=r['n_trades']))
out['param']=pd.DataFrame(rows)
# 3 約定方式
ib=pd.read_pickle('data/intrabar.pkl')
rows=[]
for lab,c,ex in [('月末引け(MOC)',CM,None),('翌営業日引け',C,None),('月中アラート当日引け',replace(C,exec_lag=0),ib)]:
    for infl in [False,True]:
        r,h,t=run(daily,s,replace(c,infl_adj=infl),exec_dates=ex); rows.append(dict(exec=lab,infl=infl,final=r['final_after_liq'],irr=r['irr'],mdd=r['mdd_twr'],trades=r['n_trades']))
out['exec']=pd.DataFrame(rows)
pd.to_pickle(out,'data/robust.pkl')
pd.set_option('display.width',200)
for k,v in out.items():
    v=v.copy(); v['final億']=(v.final/1e8).round(2); v['irr']=(v.irr*100).round(1); v['mdd']=(v.mdd*100).round(0)
    if 'contrib' in v: v['倍率']=(v.final/v.contrib).round(1)
    print('=====',k); print(v.drop(columns=['final']+(['contrib'] if 'contrib' in v else [])).to_string())
