"""
Excel数式突合ブック作成：Pythonの結果をExcel数式で独立再計算し、一致フラグを付ける。
  1) 月末判定（売りライン・買い戻しライン・高値比・状態）
  2) ゴールドプラス持ちっぱなしの日次NAV（合成式）
  3) S2日次NAVから年率・最大下落を数式で再計算
  4) ブリッジ売買の損益
使い方: python3 build_excel.py data out <finalist_signal>
"""
import sys, json
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill
sys.path.insert(0, ".")
import s2engine as E

DATA, OUT = sys.argv[1], sys.argv[2]
mkt = E.load_market(DATA); assets = E.build_assets(mkt); judg = E.judge_states(mkt)
wb = Workbook()
bold = Font(bold=True); ok_fill = PatternFill("solid", fgColor="C6EFCE")

# ---------------- 1) 月末判定 ----------------
ws = wb.active; ws.title = "月末判定"
hdr = ["月末日", "QQQ終値", "売りライン(式)", "買い戻しライン(式)", "高値比(式)", "状態(式)", "状態(Python)", "一致"]
ws.append(hdr)
j = judg.reset_index()
for r, row in enumerate(j.itertuples(), start=2):
    ws.cell(r, 1, row.date.to_pydatetime()).number_format = "yyyy-mm-dd"
    ws.cell(r, 2, float(row.qqq))
    if r >= 14:  # 12ヶ月分の過去が必要
        ws.cell(r, 3, f"=MAX(B{r-12}:B{r-1})*0.85")
        ws.cell(r, 4, f"=AVERAGE(B{r-9}:B{r-1})")
        ws.cell(r, 5, f"=B{r}/MAX(B{r-11}:B{r})-1")
        prev = f'IF(ROW()=14,"NORMAL",F{r-1})'
        on_prev = f'({prev}<>"RETREAT")'
        on_now = f'IF({on_prev},B{r}>=C{r},B{r}>=D{r})'
        ws.cell(r, 6, f'=IF({on_now},IF(E{r}>=-0.1,"NORMAL","DIP"),"RETREAT")')
        ws.cell(r, 7, row.state if isinstance(row.state, str) else "")
        ws.cell(r, 8, f'=IF(F{r}=G{r},1,0)')
ws.cell(1, 10, "一致数"); ws.cell(1, 11, f"=SUM(H14:H{len(j)+1})"); ws.cell(2, 10, "判定数"); ws.cell(2, 11, f"=COUNTA(G14:G{len(j)+1})")
for c in range(1, 9): ws.cell(1, c).font = bold

# ---------------- 2) GP持ちっぱなし ----------------
ws2 = wb.create_sheet("GP合成NAV")
ws2.append(["日付", "QQQ", "USDJPY", "金", "短期金利(年)", "GP日次リターン(式)", "GP NAV(式)", "GP NAV(Python)"])
sub = mkt[(mkt.index >= "2000-04-01") & (mkt.index <= "2026-10-31")]
gp_py = (1 + assets.loc[sub.index, "GP"]).cumprod(); gp_py = gp_py / gp_py.iloc[0]
fee = E.FEES["GP"]
for r, (d, row) in enumerate(sub.iterrows(), start=2):
    ws2.cell(r, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    ws2.cell(r, 2, float(row.qqq)); ws2.cell(r, 3, float(row.fx)); ws2.cell(r, 4, float(row.gold)); ws2.cell(r, 5, float(row.rate))
    if r == 2:
        ws2.cell(r, 6, 0.0); ws2.cell(r, 7, 1.0)
    else:
        ws2.cell(r, 6, f"=(B{r}/B{r-1})*(C{r}/C{r-1})-1+(D{r}/D{r-1})*(C{r}/C{r-1})-1-E{r}/252-{fee}/252")
        ws2.cell(r, 7, f"=G{r-1}*(1+F{r})")
    ws2.cell(r, 8, float(gp_py.iloc[r - 2]))
n2 = len(sub) + 1
ws2.cell(1, 10, "最終NAV 式"); ws2.cell(1, 11, f"=G{n2}"); ws2.cell(2, 10, "最終NAV Python"); ws2.cell(2, 11, f"=H{n2}")
ws2.cell(3, 10, "差(%)"); ws2.cell(3, 11, f"=K1/K2-1")
ws2.cell(4, 10, "年率 式"); ws2.cell(4, 11, f"=K1^(365.25/(A{n2}-A2))-1")
for c in range(1, 9): ws2.cell(1, c).font = bold

# ---------------- 3) S2 NAV → 年率・最大下落 ----------------
ws3 = wb.create_sheet("S2指標再計算")
nav = pd.read_csv(f"{OUT}/s2_nav.csv", parse_dates=["date"], index_col="date").iloc[:, 0]
stats = json.load(open(f"{OUT}/stats.json"))
ws3.append(["日付", "S2 NAV(Python)", "最高値(式)", "下落率(式)"])
for r, (d, v) in enumerate(nav.items(), start=2):
    ws3.cell(r, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"; ws3.cell(r, 2, float(v))
    ws3.cell(r, 3, f"=MAX($B$2:B{r})"); ws3.cell(r, 4, f"=B{r}/C{r}-1")
n3 = len(nav) + 1
ws3.cell(1, 6, "年率(式)"); ws3.cell(1, 7, f"=(B{n3}/B2)^(365.25/(A{n3}-A2))-1")
ws3.cell(2, 6, "年率(Python)"); ws3.cell(2, 7, float(stats["S2"]["CAGR"]))
ws3.cell(3, 6, "最大下落(式)"); ws3.cell(3, 7, f"=MIN(D2:D{n3})")
ws3.cell(4, 6, "最大下落(Python)"); ws3.cell(4, 7, float(stats["S2"]["MaxDD"]))
ws3.cell(5, 6, "一致(差<0.01pt)"); ws3.cell(5, 7, f"=IF(AND(ABS(G1-G2)<0.0001,ABS(G3-G4)<0.0001),1,0)")
for c in range(1, 5): ws3.cell(1, c).font = bold

# ---------------- 4) ブリッジ売買 ----------------
ws4 = wb.create_sheet("ブリッジ売買")
ws4.append(["日付", "区分", "金額(円)", "価格", "損益(Python, 税引後)", "損益(式, 税引前)", "備考"])
try:
    bl = pd.read_csv(f"{OUT}/finalist_bridge_log.csv", parse_dates=["date"])
    last_buy_row = None
    for r, row in enumerate(bl.itertuples(), start=2):
        ws4.cell(r, 1, row.date.to_pydatetime()).number_format = "yyyy-mm-dd"
        ws4.cell(r, 2, row.kind); ws4.cell(r, 3, float(row.amount)); ws4.cell(r, 4, float(row.price))
        if row.kind == "BUY":
            last_buy_row = r
        else:
            ws4.cell(r, 5, float(row.pnl) if pd.notna(row.pnl) else None)
            if last_buy_row:
                ws4.cell(r, 6, f"=C{last_buy_row}*(D{r}/D{last_buy_row}-1)")
                ws4.cell(r, 7, "式は税引前・スリッページ前。Python は税引後")
except FileNotFoundError:
    ws4.cell(2, 1, "ブリッジ候補なし")
for c in range(1, 8): ws4.cell(1, c).font = bold

for w in wb.worksheets:
    for col in range(1, 12): w.column_dimensions[get_column_letter(col)].width = 16
path = f"{OUT}/S2_TQQQブリッジ_Excel突合.xlsx"
wb.save(path); print("saved", path)
