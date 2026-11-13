"""LibreOfficeで再計算した候補8のExcelを読み、Pythonと突合（./recalc.sh "out/MPI_ver4_候補8_10年窓と最大下落率.xlsx" の後）"""
import openpyxl, pandas as pd, sys
wb = openpyxl.load_workbook('out/recalc/MPI_ver4_候補8_10年窓と最大下落率.xlsx', data_only=True)
rp = pd.read_pickle('data/candidate8_report.pkl'); V = rp['VERIFY']; ok = True
def chk(n, v, tol):
    global ok
    g = isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) <= tol; ok &= g; print(f'{"OK " if g else "NG "} {n}: {v}')
for tag in ('窓_10年', '窓_5年', '窓_月3万'):
    r, c = V[tag]; chk(f'{tag} 窓の値（締め日21通りの中央値）最大|乖離率|', wb[tag].cell(r, c).value, 1e-9)
for sn, r, c, lab in V['chk']:
    chk(f'{sn} {lab}', wb[sn].cell(r, c).value, 1e-9)
bad = 0
for sn, r, c, py, lab in V['text']:
    x = wb[sn].cell(r, c).value
    if x != py:
        bad += 1; print('NG ', lab, 'Excel=', x, 'Python=', py)
ok &= bad == 0; print(f'{"OK " if bad == 0 else "NG "} 判定・勝ち負けの文字と個数 {len(V["text"])}セル: 不一致 {bad}')
ws = wb['判定']
for k_, d in rp['DEC'].items():
    pass
ws = wb['検算_12か月線']; chk('12か月線 シグナル不一致数', ws['Q2'].value, 0)
for v, nm in rp['LED'].items():
    ws = wb[nm]
    chk(f'台帳({v}) 総資産 最大|乖離率|', ws['AE11'].value, 1e-9)
    chk(f'台帳({v}) 最大下落率の差', ws['AE16'].value, 1e-12)
    chk(f'台帳({v}) 開始時の状態の差', ws['AE8'].value - ws['AE9'].value, 0)
    chk(f'台帳({v}) 2倍を持った日数の差', ws['AE17'].value - ws['AE18'].value, 0)
    print('    最終 Excel=', round(ws['AE12'].value), ' Python=', round(ws['AE13'].value), ' 最大下落率 Excel=', round(ws['AE14'].value, 6), ' Python=', round(ws['AE15'].value, 6))
print('総合:', '全て一致' if ok else '不一致あり'); sys.exit(0 if ok else 1)
