"""LibreOfficeで再計算したExcel（out_imp/recalc/）を読み、Pythonの値と照合する"""
import sys, json
from openpyxl import load_workbook
wb = load_workbook("out_imp/recalc/S2改良検証_Excel突合.xlsx", data_only=True)
s0 = wb["突合の結果"]
ok = True
for r in range(4, s0.max_row + 1):
    lbl, sh, val, exp, judge = (s0.cell(r, c).value for c in range(1, 6))
    if lbl is None:
        continue
    print(f"{lbl:28s} 式の結果={val!r:>24} 期待={exp!r:>10} → {judge}")
    ok &= (judge == "一致")
# 主要な指標を並べて表示
ss = wb["指標の突合"]
print("\n系列 / 年率(式) 年率(Py) / ソルティノ(式) (Py) / 最大下落(式) (Py) / 前半 / 後半 / 最大差")
for r in range(2, ss.max_row + 1):
    v = [ss.cell(r, c).value for c in range(1, 14)]
    if v[0] is None:
        continue
    print(v[0], [round(x, 6) if isinstance(x, float) else x for x in v[1:]])
sv = wb["ボラ・有事判定"]
print("ブレーキ条件の日数(式)", sv["Q3"].value, "有事条件の日数(式)", sv["Q4"].value)
print("Excel突合", "全項目一致" if ok else "不一致あり")
sys.exit(0 if ok else 1)
