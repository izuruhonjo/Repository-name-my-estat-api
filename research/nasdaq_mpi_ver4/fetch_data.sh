#!/usr/bin/env bash
# データ取得（Yahoo Finance / FRED）。data/ に保存
set -e
mkdir -p data && cd data
for s in %5ENDX TQQQ QQQ QQQM QLD; do
  curl -sS -A "Mozilla/5.0" -o "$s.json" "https://query1.finance.yahoo.com/v8/finance/chart/$s?period1=0&period2=9999999999&interval=1d&events=div,split"
done
for id in DTB3 DEXJPUS; do curl -sS -o "$id.csv" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$id"; done
python3 - <<'PY'
import json,pandas as pd
for s in ['%5ENDX','TQQQ','QQQ','QQQM','QLD']:
    j=json.load(open(s+'.json'))['chart']['result'][0]; q=j['indicators']['quote'][0]
    df=pd.DataFrame({'o':q['open'],'h':q['high'],'l':q['low'],'c':q['close']},index=pd.to_datetime(j['timestamp'],unit='s').normalize())
    ac=j['indicators'].get('adjclose',[{}])[0].get('adjclose')
    if ac: df['adj']=ac
    df=df.dropna(subset=['c']); df=df[~df.index.duplicated(keep='last')]
    df.to_csv(s.replace('%5E','')+'_daily.csv')
PY
