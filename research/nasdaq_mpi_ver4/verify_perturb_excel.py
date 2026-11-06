"""LibreOfficeで再計算した摂動テストExcelの数式値を読み、Pythonと突合（out/recalc/ に再計算済みファイルが必要）"""
import openpyxl, pandas as pd, sys
wb = openpyxl.load_workbook('out/recalc/MPI_ver4_摂動テスト.xlsx', data_only=True)
rp = pd.read_pickle('data/perturb_report.pkl')
ok = True
def chk(name, v, tol):
    global ok
    good = isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) <= tol
    ok &= good; print(f'{"OK " if good else "NG "} {name}: {v}')
def kv(ws, col_label):
    return {r[0]: r[1] for r in ws.iter_rows(min_col=col_label, max_col=col_label + 1, values_only=True) if r[0]}
for k, (name, nb) in rp['SH'].items():
    ws = wb[name]
    sc = [x.value for x in ws[1]].index('終値差') + 3      # 集計欄の列（1始まり、最終列の2つ右）
    v = {ws.cell(r, sc).value: ws.cell(r, sc + 1).value for r in range(3, 9)}
    chk(f'k={k:+d} 足の数 Excel-Python', v['足の数'] - nb, 0)
    chk(f'k={k:+d} シグナル不一致数（日次生データ→月足→MACD→PSAR→シグナルを数式で）', v['シグナル不一致数(数式)'], 0)
    print(f'    シグナル本数(Excel)={v["シグナル本数(数式)"]}')
    chk(f'k={k:+d} 最大|PSAR差|(相対)', v['最大|PSAR差|(相対)'], 1e-9)
    chk(f'k={k:+d} 最大|高安終値差|', v['最大|高安終値差|'], 0)
ws = wb[f'検算_台帳{rp["KL"]:+d}']; v = {ws.cell(r, 27).value: ws.cell(r, 28).value for r in range(1, 11)}
chk(f'台帳 k={rp["KL"]:+d}（数式シグナル→日次台帳）最大|乖離率|', v['最大|乖離率|'], 1e-9)
chk('台帳 約定シグナル数の差', v['約定シグナル数(数式)'] - v['期間内シグナル数(Py)'], 0)
print('    最終 Excel=', round(v['最終(数式)']), ' Python=', round(v['最終(Python)']))
ws = wb['概要']; chk('概要 中央値・最小・最大・勝ち数の最大|差|', ws['B28'].value, 1e-3)
ws = wb['P3エピソード除去']; rows = {r[5]: r[6] for r in ws.iter_rows(min_row=2, values_only=True) if r[5]}
chk('P3 半分以下の組数 Excel-Python', rows['半分以下になる組の数(数式)'] - rp['n_ep_half'], 0)
chk('P3 対数比 最大|差|', rows['最大|対数比の差|(数式)'], 1e-12)
print('総合:', '全て一致' if ok else '不一致あり'); sys.exit(0 if ok else 1)
