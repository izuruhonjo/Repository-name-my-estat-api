"""LibreOfficeで再計算したExcel（out_tm/recalc/）を読み、突合の結果を表示する"""
import sys
from openpyxl import load_workbook
wb = load_workbook("out_tm/recalc/総合マニュアル_Excel突合.xlsx", data_only=True, read_only=True)
ws = wb["突合の結果"]
n = n_ok = 0; bad = []
for r in ws.iter_rows(min_row=2, values_only=True):
    lab, sh, val, py, diff, tol, judge = r[:7]
    if lab is None: continue
    n += 1
    if judge == "一致" and val is not None: n_ok += 1
    else: bad.append((lab, val, py, diff, judge))
for x in bad: print("不一致:", x)
wi = wb["指標"]
print("例：世帯の年率(式)", [c for c in next(wi.iter_rows(min_row=4, max_row=4, values_only=True))][:4])
print(f"一致 {n_ok} / {n}")
sys.exit(0 if n_ok == n else 1)
