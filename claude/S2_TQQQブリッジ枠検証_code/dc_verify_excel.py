"""LibreOfficeで再計算したExcel（out_dc/recalc/）を読み、Pythonの値と照合する"""
import sys
from openpyxl import load_workbook

wb = load_workbook("out_dc/recalc/DC規則の一斉比較_Excel突合.xlsx", data_only=True, read_only=True)
ws = wb["突合の結果"]
rows = list(ws.iter_rows(min_row=2, values_only=True))
ok = True
n_ok = 0
n = 0
for r in rows:
    lab, sh, val, py, diff, tol, judge = r[:7]
    if lab is None:
        continue
    n += 1
    flag = judge == "一致"
    n_ok += flag
    ok &= flag
    print(f"{lab:40s} 式={val!r:>24} Python={py!r:>24} 差={diff!r:>12} → {judge}")
print(f"\n一致 {n_ok} / {n}")
print("Excel突合", "全項目一致" if ok else "不一致あり")
sys.exit(0 if ok else 1)
