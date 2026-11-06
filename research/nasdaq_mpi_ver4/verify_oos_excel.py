"""LibreOfficeで再計算したExcelの数式値を読み、Pythonと突合（out/recalc/ に再計算済みファイルが必要）"""
import openpyxl, pandas as pd, sys
wb = openpyxl.load_workbook('out/recalc/MPI_ver4_OOS検証.xlsx', data_only=True)
rp = pd.read_pickle('data/oos_report.pkl'); o = pd.read_pickle('data/oos.pkl')
ok = True
def chk(name, v, tol):
    global ok
    good = isinstance(v, (int, float)) and abs(v) <= tol
    ok &= good; print(f'{"OK " if good else "NG "} {name}: {v}')
ws = wb['検算_月次台帳']; n = rp['LEDGER_N']
chk('月次台帳(S&P500 1950-85, 6%monthly, 日次生データから数式) 最大|乖離率|', ws.cell(n + 2, 3).value, 1e-9)
print('    2倍だった月数(Excel)=', ws.cell(n + 3, 3).value, ' 最終 Excel=', round(ws.cell(n, 28).value), ' Python=', round(ws.cell(n, 29).value))
ws = wb['検算_MACD']; chk('MACD(12,26)', ws['M1'].value, 1e-9); chk('シグナル(9)', ws['M2'].value, 1e-9)
ws = wb['窓集計']; k = rp['WS_ROWS']; chk('窓集計 勝数の差', ws.cell(k + 2, 3).value, 0); chk('窓集計 中央値の差', ws.cell(k + 3, 3).value, 1e-12)
ws = wb['①IS選択']; vals = {r[0]: r[1] for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}
print(('OK ' if vals.get('一致(数式)') is True else 'NG '), 'IS選択 Excel=', vals.get('Excelが選んだ案(数式)'), ' Python=', vals.get('Pythonが選んだ案'))
ok &= vals.get('一致(数式)') is True
r = o['res']; f = r[r.win == '全期間']
ws = wb['概要']; rows = list(ws.iter_rows(min_row=1, values_only=True))
sets = rows[4][1:8]; i0 = [i for i, x in enumerate(rows) if x[0] and str(x[0]).startswith('倍率')][0]
mx = 0
for x in rows[i0 + 1:i0 + 8]:
    for s, v in zip(sets, x[1:8]):
        g = f[(f.set == s) & (f['var'] == x[0])].iloc[0]; mx = max(mx, abs(v / (g.final / g.contrib) - 1))
chk('概要 倍率(数式) vs Python', mx, 1e-12)
print('総合:', '全て一致' if ok else '不一致あり'); sys.exit(0 if ok else 1)
