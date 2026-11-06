#!/usr/bin/env bash
# データ取得（Yahoo Finance / FRED）。data/ に保存
set -e
mkdir -p data && cd data
for s in %5ENDX TQQQ QQQ QQQM QLD; do
  curl -sS -A "Mozilla/5.0" -o "$s.json" "https://query1.finance.yahoo.com/v8/finance/chart/$s?period1=0&period2=9999999999&interval=1d&events=div,split"
done
# OOS検証用（1927年〜を取るため period1 を負に）
for s in %5EGSPC %5EIXIC %5EDJI %5ERUT UPRO SSO UDOW DDM TNA UWM SPY DIA IWM; do
  curl -sS -A "Mozilla/5.0" -o "$s.json" "https://query1.finance.yahoo.com/v8/finance/chart/$s?period1=-1500000000&period2=9999999999&interval=1d&events=div,split"
done
# Shiller の S&P500 月次配当（github.com/datasets/s-and-p-500 経由）
rm -rf /tmp/sp500ds && git clone -q --depth 1 https://github.com/datasets/s-and-p-500.git /tmp/sp500ds && cp /tmp/sp500ds/data/data.csv shiller_sp500.csv
for id in DTB3 DEXJPUS TB3MS; do curl -sS -o "$id.csv" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$id"; done
python3 - <<'PY'
import json,pandas as pd
for s in ['%5ENDX','TQQQ','QQQ','QQQM','QLD','%5EGSPC','%5EIXIC','%5EDJI','%5ERUT','UPRO','SSO','UDOW','DDM','TNA','UWM','SPY','DIA','IWM']:
    j=json.load(open(s+'.json'))['chart']['result'][0]; q=j['indicators']['quote'][0]
    df=pd.DataFrame({'o':q['open'],'h':q['high'],'l':q['low'],'c':q['close']},index=pd.to_datetime(j['timestamp'],unit='s').normalize())
    ac=j['indicators'].get('adjclose',[{}])[0].get('adjclose')
    if ac: df['adj']=ac
    df=df.dropna(subset=['c']); df=df[~df.index.duplicated(keep='last')]
    df.to_csv(s.replace('%5E','')+'_daily.csv')
PY
