"""LibreOfficeで再計算した単純ルール比較Excelの数式値を読み、Pythonと突合（out/recalc/ に再計算済みファイルが必要）"""
import openpyxl, pandas as pd, sys
wb = openpyxl.load_workbook('out/recalc/MPI_ver4_単純ルール比較.xlsx', data_only=True)
rp = pd.read_pickle('data/simple_report.pkl')
ok = True
def chk(name, v, tol):
    global ok
    good = isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) <= tol
    ok &= good; print(f'{"OK " if good else "NG "} {name}: {v}')
ws = wb['概要']
chk('概要 中央値(万円)・勝ち数の最大|差|', ws.cell(rp['SUMROW'], 2).value, 1e-6)
rows = [r for r in ws.iter_rows(values_only=True) if r[0]]
cnt = [r for r in rows if str(r[0]).startswith('上回ったセット数')]
for (r, m) in zip(cnt, rp['n_dec']):
    chk(f'判定 上回ったセット数 Excel-Python ({m})', r[1] - r[3], 0)
for r in rows:
    if r[0] == '結論(数式)': print('    結論:', r[1])
ws = wb['10年窓集計']; chk('10年窓 勝ち数の最大|差|', ws.cell(rp['WROW'], 2).value, 0)
ws = wb['検算_12か月線']; sc = rp['sc'] + 1
v = {ws.cell(r, sc).value: ws.cell(r, sc + 1).value for r in range(2, 5)}
chk('12か月線 シグナル不一致数（日次生データ→月足→12か月平均→シグナルを数式で）', v['シグナル不一致数(数式)'], 0)
print('    シグナル本数(Excel)=', v['シグナル本数(数式)'])
chk('12か月線 月足終値の最大|差|', v['終値の最大|差|'], 0)
ws = wb['検算_台帳_一括']; v = {ws.cell(r, 28).value: ws.cell(r, 29).value for r in range(1, 14)}
print('    開始時の状態 Excel=', v['開始時の状態(数式)'], ' Python=', v['開始時の状態(Python)'])
ok &= (v['開始時の状態(数式)'] == 1) == (v['開始時の状態(Python)'] == 'long')
chk('台帳(100万円一括・12か月線・数式シグナル) 最大|乖離率|', v['最大|乖離率|'], 1e-9)
chk('台帳 約定シグナル数の差', v['約定シグナル数(数式)'] - v['約定シグナル数(Py)'], 0)
print('    最終 Excel=', round(v['最終(数式)']), ' Python=', round(v['最終(Python)']))
print('総合:', '全て一致' if ok else '不一致あり'); sys.exit(0 if ok else 1)
