"""LibreOfficeで再計算した候補7のExcelを読み、Pythonと突合"""
import openpyxl, pandas as pd, sys
wb = openpyxl.load_workbook('out/recalc/MPI_ver4_候補7_置き場と2倍.xlsx', data_only=True)
rp = pd.read_pickle('data/candidate7_report.pkl'); ok = True
def chk(n, v, tol):
    global ok
    g = isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) <= tol; ok &= g; print(f'{"OK " if g else "NG "} {n}: {v}')
ws = wb['判定']
chk('中央値(万円) 112セル 最大|差|', ws.cell(rp['SUMROW'], 2).value, 1e-6)
for m, (ex, n2, lv) in rp['DEC'].items():
    r = rp['DECROW'][(m, 'n2')]
    chk(f'{m} 手順2 2倍が良いOOSセット数 Excel-Python', ws.cell(r, 4).value - n2, 0)
    # 手順1: Excel で合格かつ勝ち数最大の置き場 = Python の選択
    r1 = rp['DECROW'][(m, 'exit')]
    cand = [(ws.cell(r1 - 3 + i, 1).value, ws.cell(r1 - 3 + i, 3).value, ws.cell(r1 - 3 + i, 4).value) for i in range(3)]
    passed = [c for c in cand if c[1] is True]
    exx = max(passed, key=lambda c: c[2])[0] if passed else 'drip'
    good = exx == ex; ok &= good; print(f'{"OK " if good else "NG "} {m} 手順1 Excel={exx} Python={ex} 候補={cand}')
ws = wb['検算_12か月線']; chk('12か月線 シグナル不一致数', ws['Q2'].value, 0)
for mode_, nm in rp['LED'].items():
    ws = wb[nm]; chk(f'台帳({mode_}) 最大|乖離率|', ws['AD9'].value, 1e-9)
    print('    最終 Excel=', round(ws['AD10'].value), ' Python=', round(ws['AD11'].value), ' 開始状態', ws['AD6'].value, ws['AD7'].value)
print('総合:', '全て一致' if ok else '不一致あり'); sys.exit(0 if ok else 1)
