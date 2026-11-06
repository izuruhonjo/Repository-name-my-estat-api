"""K0詳細版マニュアルのExcel突合：日次NAV（K0・K0換金後）から22指標・年次・月次を数式で再計算してPythonと照合"""
import sys
sys.path.insert(0, ".")
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter as L

nav = pd.read_csv("out_k0/k0_nav.csv", index_col=0, parse_dates=True)
I = pd.read_csv("out_k0/indicators.csv", index_col=0)
Y = pd.read_csv("out_k0/yearly.csv", index_col=0)
MT = pd.read_csv("out_k0/monthly_table.csv", index_col=0)
SER = ["K0", "K0換金後"]
b = Font(bold=True)
wb = Workbook(); wd = wb.active; wd.title = "日次"
n = len(nav); R0, Rl = 3, 3 + n - 1
wd.cell(1, 1, "日付").font = b
SUB = ["NAV(Python)", "日次リターン(式)", "下落日(式)", "高値(式)", "高値からの下落(式)", "高値の日(式)", "水面下日数(式)"]
for j, s in enumerate(SER):
    c0 = 2 + j * 7; wd.cell(1, c0, s).font = b
    for t, h in enumerate(SUB): wd.cell(2, c0 + t, h)
for r, d in enumerate(nav.index):
    R = R0 + r
    wd.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    for j, s in enumerate(SER):
        c0 = 2 + j * 7; N, RT, NG, RM, DD, PD, UW = (L(c0 + k) for k in range(7))
        wd.cell(R, c0, float(nav[s].iloc[r]))
        if r > 0:
            wd.cell(R, c0 + 1, f"={N}{R}/{N}{R-1}-1"); wd.cell(R, c0 + 2, f'=IF({RT}{R}<-1E-12,{RT}{R},"")')
            wd.cell(R, c0 + 3, f"=MAX({RM}{R-1},{N}{R})")
            wd.cell(R, c0 + 5, f"=IF({N}{R}>={RM}{R},A{R},{PD}{R-1})")
        else:
            wd.cell(R, c0 + 3, f"={N}{R}"); wd.cell(R, c0 + 5, f"=A{R}")
        wd.cell(R, c0 + 4, f"={N}{R}/{RM}{R}-1"); wd.cell(R, c0 + 6, f"=A{R}-{PD}{R}")

# 月末・年末シート
me = nav.resample("ME").last().index
wm = wb.create_sheet("月次")
wm.cell(1, 1, "月末").font = b
for j, s in enumerate(SER):
    wm.cell(1, 2 + j * 3, f"{s} 月末NAV(式)").font = b; wm.cell(1, 3 + j * 3, f"{s} 月次(式)").font = b; wm.cell(1, 4 + j * 3, f"{s} 5年年率(式)").font = b
wm.cell(2, 1, "開始日")
for j, s in enumerate(SER):
    wm.cell(2, 2 + j * 3, f"=日次!{L(2+j*7)}{R0}")
for k, d in enumerate(me):
    R = 3 + k
    wm.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    for j, s in enumerate(SER):
        N = L(2 + j * 7); cm, cr, c5 = L(2 + j * 3), L(3 + j * 3), L(4 + j * 3)
        wm.cell(R, 2 + j * 3, f"=LOOKUP(A{R},日次!$A${R0}:$A${Rl},日次!{N}${R0}:{N}${Rl})")
        wm.cell(R, 3 + j * 3, f"={cm}{R}/{cm}{R-1}-1")
        if k >= 60: wm.cell(R, 4 + j * 3, f"=({cm}{R}/{cm}{R-60})^(1/5)-1")
Rm = 3 + len(me) - 1
wy = wb.create_sheet("年次")
years = list(range(2000, 2027))
wy.cell(1, 1, "年").font = b
for j, s in enumerate(SER):
    wy.cell(1, 2 + j * 4, f"{s} 年末NAV(式)").font = b; wy.cell(1, 3 + j * 4, f"{s} 年リターン(式)").font = b
    wy.cell(1, 4 + j * 4, f"{s} 年リターン(Python)").font = b; wy.cell(1, 5 + j * 4, "差").font = b
for k, y in enumerate(years):
    R = 2 + k; wy.cell(R, 1, y)
    for j, s in enumerate(SER):
        N = L(2 + j * 7); cn = L(2 + j * 4)
        wy.cell(R, 2 + j * 4, f"=LOOKUP(DATE({y},12,31),日次!$A${R0}:$A${Rl},日次!{N}${R0}:{N}${Rl})")
        prev = f"日次!{N}${R0}" if k == 0 else f"{cn}{R-1}"
        wy.cell(R, 3 + j * 4, f"={cn}{R}/{prev}-1"); wy.cell(R, 4 + j * 4, float(Y.loc[y, s]))
        wy.cell(R, 5 + j * 4, f"=ABS({L(3+j*4)}{R}-{L(4+j*4)}{R})")
Ry = 1 + len(years)

# 指標シート
wi = wb.create_sheet("22指標", 0)
wi.cell(1, 1, "K0（マニュアルどおりのS2）22指標：日次NAVから数式で再計算").font = b
hdr = ["指標"] + sum([[f"{s}(式)", f"{s}(Python)", "差"] for s in SER], [])
for j, h in enumerate(hdr, 1): wi.cell(3, j, h).font = b
def f(s, key):
    j = SER.index(s); N, RT, NG, RM, DD, PD, UW = (L(2 + j * 7 + k) for k in range(7))
    cm, cr, c5 = L(2 + j * 3), L(3 + j * 3), L(4 + j * 3); cy = L(3 + j * 4)
    yrs = f"((日次!A{Rl}-日次!A{R0})/365.25)"
    cagr = f"((日次!{N}{Rl}/日次!{N}{R0})^(1/{yrs})-1)"
    vol = f"(STDEV(日次!{RT}{R0+1}:{RT}{Rl})*SQRT(252))"
    mdd = f"MIN(日次!{DD}{R0}:{DD}{Rl})"
    mr = f"月次!{cr}3:{cr}{Rm}"; yr = f"年次!{cy}2:{cy}{Ry}"
    var = f"PERCENTILE({mr},0.05)"
    last = f"日次!A{Rl}"
    def ago(m): return f"LOOKUP(EDATE({last},{-m}),日次!$A${R0}:$A${Rl},日次!{N}${R0}:{N}${Rl})"
    return {"年率（CAGR）": cagr, "累積倍率": f"日次!{N}{Rl}/日次!{N}{R0}", "年率ボラ": vol, "シャープ（無リスク0）": f"{cagr}/{vol}",
            "ソルティノ": f"{cagr}/(STDEV(日次!{NG}{R0+1}:{NG}{Rl})*SQRT(252))", "最大下落": mdd, "カルマー": f"{cagr}/ABS({mdd})",
            "水面下の最長日数": f"MAX(日次!{UW}{R0}:{UW}{Rl})", "アルサー指数": f"SQRT(SUMSQ(日次!{DD}{R0}:{DD}{Rl})/COUNT(日次!{DD}{R0}:{DD}{Rl}))",
            "最悪の年": f"MIN({yr})", "最良の年": f"MAX({yr})", "プラスの年の割合": f'COUNTIF({yr},">0")/COUNT({yr})',
            "月次の勝率": f'COUNTIF({mr},">0")/COUNT({mr})', "最悪の月": f"MIN({mr})", "最良の月": f"MAX({mr})", "月次VaR95": var,
            "月次CVaR95": f'AVERAGEIF({mr},"<="&{var})', "月次の歪度": f"SKEW({mr})", "月次の尖度（超過）": f"KURT({mr})",
            "5年続けたときの最悪の年率": f"MIN(月次!{c5}3:{c5}{Rm})", "直近5年の年率": f"(日次!{N}{Rl}/{ago(60)})^(1/5)-1",
            "直近1年": f"日次!{N}{Rl}/{ago(12)}-1"}[key]
for k, key in enumerate(I.index):
    R = 4 + k; wi.cell(R, 1, key)
    for j, s in enumerate(SER):
        c = 2 + j * 3
        wi.cell(R, c, "=" + f(s, key)); wi.cell(R, c + 1, float(I.loc[key, s]))
        wi.cell(R, c + 2, f"=ABS({L(c)}{R}-{L(c+1)}{R})/MAX(1,ABS({L(c+1)}{R}))")
Ri = 3 + len(I)
wi.cell(Ri + 2, 1, "指標の最大差（相対）").font = b; wi.cell(Ri + 2, 2, f"=MAX(D4:D{Ri},G4:G{Ri})")
wi.cell(Ri + 3, 1, "年次リターンの最大差").font = b; wi.cell(Ri + 3, 2, f"=MAX(年次!E2:E{Ry},年次!I2:I{Ry})")
# 月次表（K0）の照合：月次シートの式とPythonの月次表
d = 0
wi.cell(Ri + 4, 1, "月次リターン表の最大差").font = b
pairs = []
for k, dt in enumerate(me):
    v = MT.loc[dt.year, str(dt.month)]
    pairs.append(f"ABS(月次!C{3+k}-{float(v)!r})")
wi.cell(Ri + 4, 2, "=MAX(" + ",".join(pairs[:200]) + ")"); wi.cell(Ri + 4, 3, "=MAX(" + ",".join(pairs[200:]) + ")")
wb.save("out_k0/K0_Excel突合.xlsx")
print("saved", Ri)
