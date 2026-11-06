import sys; sys.path.insert(0,'.')
from mpi import *
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt, matplotlib.ticker as mt
from matplotlib import font_manager
font_manager.fontManager.addfont('/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf')
plt.rcParams.update({'font.family':'IPAGothic','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':0.25})
OUT=Path('./out')
series,contrib=pd.read_pickle('data/series.pkl'); attr=pd.read_pickle('data/attr.pkl'); rob=pd.read_pickle('data/robust.pkl')
COL={'MPI 記事条件(A)':'#9e9e9e','MPI 現実コスト(C-MOC 月末引け)':'#1f4e9e','MPI 現実コスト(C 翌営業日)':'#5b8bd6','TQQQ単純積立(C)':'#d0632a','QQQM単純積立(C)':'#2e9e5b'}
def oku(x,_): 
    return f'{x/1e8:,.0f}億' if x>=1e8 else (f'{x/1e4:,.0f}万')
# 1 時系列
fig,ax=plt.subplots(figsize=(11,6),dpi=110)
for k,v in series.items():
    ax.plot(v.index,v.values,label=f"{k}  最終 {v.iloc[-1]/1e8:,.1f}億円",color=COL[k],lw=2.2 if 'C-MOC' in k else 1.6,ls='--' if '記事' in k else '-')
ax.plot(contrib.index,contrib.values,color='black',lw=1,ls=':',label=f'投入元本 {contrib.iloc[-1]/1e4:,.0f}万円')
ax.set_yscale('log'); ax.yaxis.set_major_formatter(mt.FuncFormatter(oku)); ax.set_ylim(1e4,3e10)
ax.set_title('毎月3万円(名目)積立 1985/10〜2026/10 の資産推移（円建て・税引前評価額、対数軸）',loc='left',fontsize=12,fontweight='bold')
ax.legend(loc='upper left',fontsize=9,frameon=False)
ax.text(0.99,0.02,'C=SBI手数料・為替・日本税制・ファンド内コスト込み / 記事条件=コストなし疑似3倍',transform=ax.transAxes,ha='right',fontsize=8,color='#555')
fig.tight_layout(); fig.savefig(OUT/'fig1_資産推移.png'); plt.close()
# 2 要因分解(名目3万, 2026-10)
g=attr[(attr.end=='2026-10')&(attr.infl==False)].reset_index(drop=True)
fig,ax=plt.subplots(figsize=(11,5.6),dpi=110)
vals=g.final.values/1e8; labs=g.step.values
cols=['#9e9e9e']+['#c0392b' if vals[i]<vals[i-1] else '#27ae60' for i in range(1,len(vals))]
cols[4]='#1f4e9e'; cols[-1]='#1f4e9e'
bars=ax.barh(range(len(vals))[::-1],vals,color=cols)
for i,(b,v) in enumerate(zip(bars,vals)):
    ch='' if i==0 else f'  ({(v/vals[i-1]-1)*100:+.0f}%)'
    ax.text(v+1.5,b.get_y()+b.get_height()/2,f'{v:,.1f}億円{ch}',va='center',fontsize=9)
ax.set_yticks(range(len(vals))[::-1]); ax.set_yticklabels(labs,fontsize=9); ax.set_xlim(0,vals.max()*1.3)
ax.set_xlabel('最終資産 税引後（億円）'); ax.grid(axis='y',visible=False)
ax.set_title('記事条件 → 現実コストへの要因分解（MPI ver4・名目3万円・1985/10〜2026/10）',loc='left',fontsize=12,fontweight='bold')
fig.tight_layout(); fig.savefig(OUT/'fig2_要因分解.png'); plt.close()
# 3 開始年感応度
st=rob['start'].copy(); st['mult']=st.final/st.contrib
piv=st.pivot(index='start',columns='strat',values='mult')[['MPI(C-MOC)','MPI(C 翌日)','TQQQ積立','QQQM積立']]
fig,ax=plt.subplots(figsize=(11,5.4),dpi=110)
x=np.arange(len(piv)); w=0.2
cc=['#1f4e9e','#5b8bd6','#d0632a','#2e9e5b']
for j,c in enumerate(piv.columns):
    ax.bar(x+(j-1.5)*w,piv[c].values,w,label=c,color=cc[j])
ax.set_yscale('log'); ax.set_xticks(x); ax.set_xticklabels([p[:4]+'年〜' for p in piv.index])
ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v,_: f'{v:g}倍'))
ax.set_ylabel('最終資産 ÷ 投入元本（税引後、2026/10時点）')
ax.set_title('積立開始年を変えた場合（全て現実コストC・名目3万円）— 2000年以降はMPIの優位が消える',loc='left',fontsize=12,fontweight='bold')
ax.legend(frameon=False,ncol=4,loc='upper right'); ax.grid(axis='x',visible=False)
fig.tight_layout(); fig.savefig(OUT/'fig3_開始年感応度.png'); plt.close()
# 4 パラメータ
p=rob['param']; p=p[(p.cfg=='C')&(p.psar_max.isin([0.1,0.15,0.2]))]
hm=p.pivot(index='macd',columns='psar_max',values='final')/1e8
order=['(8, 17, 9)','(10, 22, 7)','(12, 26, 9)','(14, 30, 11)','(16, 34, 12)']; hm=hm.loc[order]
fig,ax=plt.subplots(figsize=(8,5),dpi=110)
im=ax.imshow(np.log10(hm.values),cmap='Blues',aspect='auto',vmin=1,vmax=2.3)
for i in range(hm.shape[0]):
    for j in range(hm.shape[1]):
        v=hm.values[i,j]; ax.text(j,i,f'{v:,.0f}億'+(' ←記事' if order[i]=='(12, 26, 9)' and hm.columns[j]==0.2 else ''),ha='center',va='center',color='white' if np.log10(v)>1.8 else 'black',fontsize=10)
ax.set_xticks(range(hm.shape[1])); ax.set_xticklabels([f'PSAR最大値 {c}' for c in hm.columns])
ax.set_yticks(range(hm.shape[0])); ax.set_yticklabels([f'MACD{o}' for o in order]); ax.grid(False)
ax.set_title('パラメータ感応度（現実コストC・名目3万円・1985/10〜2026/10、税引後）',loc='left',fontsize=11,fontweight='bold')
fig.tight_layout(); fig.savefig(OUT/'fig4_パラメータ感応度.png'); plt.close()
print('ok')
