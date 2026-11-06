"""次の候補5（単純ルール比較・100万円一括）の Excel（数式で突合）とグラフ。前提: python3 simple_rules.py 実行済み"""
import sys
sys.path.insert(0, ".")
from simple_rules import *
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name as CN
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.ticker as mt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

OUT = Path("./out"); OUT.mkdir(exist_ok=True)
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams.update({"font.family": "IPAGothic", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, AQUA, GRAY, INK, INK2 = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984", "#0b0b0b", "#52514e"

O = pd.read_pickle("data/simple_rules.pkl"); R = O["res"]; W = O["win"]; COST = O["cost"]
SETORDER = [s[0] for s in SETS2]; KIND = {s[0]: s[1] for s in SETS2}
ALL = RULES + list(BENCH)
MODEL = list(MODES)

# Python 側の集計
MED = R.groupby(["mode", "set", "rule"]).final.median()
PW = {}
for mode in MODEL:
    p = R[(R["mode"] == mode) & R.rule.isin(RULES)].pivot_table(index=["set", "k"], columns="rule", values="final")
    for ru in RULES[1:]:
        for s in SETORDER:
            PW[(mode, s, ru)] = int((p.loc[s][ru] > p.loc[s]["MPI(ver4.0)"]).sum())
DEC = {(mode, s): bool(MED[(mode, s, "MPI(ver4.0)")] > MED[(mode, s, "10か月線")] and MED[(mode, s, "MPI(ver4.0)")] > MED[(mode, s, "12か月線")])
       for mode in MODEL for s in SETORDER}

wb = xlsxwriter.Workbook(str(OUT / "MPI_ver4_単純ルール比較.xlsx"), {"use_future_functions": True})
F = dict(h=wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True, "valign": "top", "border": 1}),
         yen=wb.add_format({"num_format": "#,##0"}), man=wb.add_format({"num_format": "#,##0"}), x2=wb.add_format({"num_format": "0.00"}),
         pct=wb.add_format({"num_format": "0.0%"}), f6=wb.add_format({"num_format": "0.000000"}), sci=wb.add_format({"num_format": "0.00E+00"}),
         title=wb.add_format({"bold": True, "font_size": 14}), b=wb.add_format({"bold": True}),
         wrap=wb.add_format({"text_wrap": True, "valign": "top"}), d=wb.add_format({"num_format": "yyyy-mm-dd"}))


def hdr(ws, r, cols, c0=0):
    for j, x in enumerate(cols):
        ws.write(r, c0 + j, x, F["h"])


RR = R.reset_index(drop=True)
NR = len(RR) + 1
# ------------------------------------------------------------------ 概要
ws = wb.add_worksheet("概要")
ws.set_column(0, 0, 30); ws.set_column(1, 8, 14)
ws.write(0, 0, "MACD＋パラボリック(ver4.0) vs 単純な暴落回避ルール（100万円スタート）", F["title"])
ws.write(1, 0, "現実コストC、締め日21通り(k=-10〜+10)の中央値。運用の仕組みは全ルール共通（買い=全額3倍、売り=現金→毎月1%ずつ1倍）。数式は「データ」シートを集計")
r = 3
CHK = []
for mode in MODEL:
    ws.write(r, 0, f"【{mode}】 税引後最終資産の中央値（万円, 数式）", F["b"]); r += 1
    hdr(ws, r, ["ルール \\ セット"] + SETORDER); hdrrow = r + 1; r += 1
    first = r + 1
    for ru in ALL:
        ws.write(r, 0, ru)
        for j, s in enumerate(SETORDER):
            c = CN(j + 1)
            cond = f'(データ!$A$2:$A${NR}="{mode}")*(データ!$B$2:$B${NR}={c}${hdrrow})*(データ!$C$2:$C${NR}=$A{r + 1})'
            ws.write_array_formula(r, j + 1, r, j + 1, f"{{=MEDIAN(IF({cond},データ!$F$2:$F${NR}))/1E4}}", F["man"])
            CHK.append((r, j + 1, MED[(mode, s, ru)] / 1e4))
        r += 1
    mpi_row = first
    ws.write(r, 0, "判定: MPIが10か月線と12か月線の両方を上回る(数式)", F["b"])
    for j, s in enumerate(SETORDER):
        c = CN(j + 1)
        ws.write_formula(r, j + 1, f"=AND({c}{mpi_row}>{c}{mpi_row + 3},{c}{mpi_row}>{c}{mpi_row + 4})")
    dec_row = r + 1; r += 1
    ws.write(r, 0, "上回ったセット数 /7(数式)", F["b"]); ws.write_formula(r, 1, f"=COUNTIF(B{dec_row}:H{dec_row},TRUE)")
    ws.write(r, 2, "Python"); ws.write_number(r, 3, sum(DEC[(mode, s)] for s in SETORDER)); r += 1
    ws.write(r, 0, "結論(数式)", F["b"])
    ws.write_formula(r, 1, f'=IF(AND(B{dec_row},COUNTIF(C{dec_row}:H{dec_row},TRUE)>=4),"MACD＋パラボリックの複雑さに意味あり","単純ルールで足りる")'); r += 2
    ws.write(r, 0, f"【{mode}】 同じ締め日でMPIに勝った数 /21（数式）", F["b"]); r += 1
    hdr(ws, r, ["ルール \\ セット"] + SETORDER); r += 1
    for ru in RULES[1:]:
        ws.write(r, 0, ru)
        for j, s in enumerate(SETORDER):
            ws.write_formula(r, j + 1, f'=COUNTIFS(データ!$A$2:$A${NR},"{mode}",データ!$B$2:$B${NR},"{s}",データ!$C$2:$C${NR},$A{r + 1},データ!$M$2:$M${NR},1)')
            CHK.append((r, j + 1, PW[(mode, s, ru)]))
        r += 1
    r += 1
ws.write(r, 0, "Python との最大|差|（中央値は万円、勝ち数は回）", F["b"])
ws.write_formula(r, 1, "=MAX(" + ",".join(f"ABS({CN(c)}{rr + 1}-{float(v)!r})" for rr, c, v in CHK) + ")", F["sci"])
SUMROW = r + 1
ws.freeze_panes(3, 1)

# ------------------------------------------------------------------ データ（全ルール×締め日×セット×資金）
ws = wb.add_worksheet("データ")
cols = ["資金", "セット", "ルール", "締め日k", "開始時の状態", "税引後最終資産(円)", "投入元本(円)", "IRR", "最大DD", "売買回数",
        "同じ締め日のMPI(円,数式)", "MPI比(数式)", "MPIに勝つ(数式)"]
hdr(ws, 0, cols); ws.set_column(0, 2, 18); ws.set_column(3, 12, 13)
RR = R.reset_index(drop=True)
NR = len(RR) + 1
for i, x in enumerate(RR.itertuples(), start=1):
    r_ = i + 1
    ws.write(i, 0, x.mode); ws.write(i, 1, x.set); ws.write(i, 2, x.rule); ws.write_number(i, 3, x.k); ws.write(i, 4, x.init)
    ws.write_number(i, 5, x.final, F["yen"]); ws.write_number(i, 6, x.contrib, F["yen"]); ws.write_number(i, 7, x.irr, F["pct"])
    ws.write_number(i, 8, x.mdd, F["pct"]); ws.write_number(i, 9, x.trades)
    if x.rule in RULES:
        ws.write_formula(i, 10, f'=SUMIFS($F$2:$F${NR},$A$2:$A${NR},A{r_},$B$2:$B${NR},B{r_},$C$2:$C${NR},"MPI(ver4.0)",$D$2:$D${NR},D{r_})', F["yen"])
        ws.write_formula(i, 11, f"=F{r_}/K{r_}", F["x2"]); ws.write_formula(i, 12, f"=IF(F{r_}>K{r_},1,0)")
ws.autofilter(0, 0, NR - 1, 12); ws.freeze_panes(1, 3)

# ------------------------------------------------------------------ 設計
ws = wb.add_worksheet("検証設計")
ws.set_column(0, 0, 22); ws.set_column(1, 1, 120)
rows_ = [("項目", "内容"),
         ("問い", "ver4.0 の MACD＋パラボリックは、単純な移動平均ルールより良いのか（複雑さに意味があるか）"),
         ("資金", "主ケース: 100万円を初日に一括・積立なし。感応度: 100万円 + 月3万円(月初)"),
         ("コスト", "現実コストC（SBI手数料0.495%上限22USD・スリッページ・為替・特定口座の税・較正済み3倍コスト）。締め日の翌営業日の引けで約定"),
         ("共通の仕組み", "買い=全額を3倍へ。売り=3倍を全売却して現金、毎月その1%を1倍へ（ver4.0と同じ）。シグナルの作り方だけ入れ替える"),
         ("開始時の状態", "開始前のシグナル履歴で決める（最後のシグナルが買いなら3倍で開始）"),
         ("ルール(固定)", "MPI(ver4.0) / MACDのみ(MACD>シグナル) / パラボリックのみ(終値>SAR) / 10か月線 / 12か月線 / 12か月モメンタム(終値>12か月前)。参考: 3倍保有・1倍保有"),
         ("検証セット", "NDX 1989/1〜2026/10（全ルールの準備期間がそろう時点から）＋前回と同じOOS 6セット"),
         ("頑健性", "月足の締め日21通り(k=-10〜+10)の分布で比較。締め日k=0で10年窓(毎年1月開始の一括)も計算"),
         ("判定(事前固定)", "MPIの21通り中央値が10か月線・12か月線の両方を、ISとOOS 6セット中4以上で上回れば『複雑さに意味あり』。満たさなければ『単純ルールで足りる』"),
         ]
for i, rr in enumerate(rows_):
    for j, x in enumerate(rr):
        ws.write(i, j, x, F["h"] if i == 0 else F["wrap"])

# ------------------------------------------------------------------ 10年窓
ws = wb.add_worksheet("10年窓")
WW = W.reset_index(drop=True); NW = len(WW) + 1
hdr(ws, 0, ["セット", "ルール", "開始", "終了", "税引後最終資産(円)", "同じ窓のMPI(円,数式)", "MPI比(数式)", "MPIに勝つ(数式)", "最大DD"])
ws.set_column(0, 1, 20); ws.set_column(2, 8, 13)
for i, x in enumerate(WW.itertuples(), start=1):
    r_ = i + 1
    ws.write(i, 0, x.set); ws.write(i, 1, x.rule); ws.write(i, 2, x.start); ws.write(i, 3, x.end)
    ws.write_number(i, 4, x.final, F["yen"])
    ws.write_formula(i, 5, f'=SUMIFS($E$2:$E${NW},$A$2:$A${NW},A{r_},$B$2:$B${NW},"MPI(ver4.0)",$C$2:$C${NW},C{r_})', F["yen"])
    ws.write_formula(i, 6, f"=E{r_}/F{r_}", F["x2"]); ws.write_formula(i, 7, f"=IF(E{r_}>F{r_},1,0)"); ws.write_number(i, 8, x.mdd, F["pct"])
ws.autofilter(0, 0, NW - 1, 8); ws.freeze_panes(1, 2)
ws = wb.add_worksheet("10年窓集計")
ws.set_column(0, 0, 20); ws.set_column(1, 9, 14)
ws.write(0, 0, "10年窓（締め日k=0、100万円一括）でMPIに勝った窓の数（数式）", F["b"])
hdr(ws, 1, ["ルール \\ セット"] + [s for s in SETORDER if s != "NDX 2022/9-2026"])
WSETS = [s for s in SETORDER if s != "NDX 2022/9-2026"]
WCHK = []
for i, ru in enumerate(ALL[1:]):
    ws.write(2 + i, 0, ru)
    for j, s in enumerate(WSETS):
        ws.write_formula(2 + i, j + 1, f'=COUNTIFS(\'10年窓\'!$A$2:$A${NW},"{s}",\'10年窓\'!$B$2:$B${NW},$A{3 + i},\'10年窓\'!$H$2:$H${NW},1)')
        g = WW[(WW.set == s) & (WW.rule == ru)].set_index("start").final
        m = WW[(WW.set == s) & (WW.rule == "MPI(ver4.0)")].set_index("start").final
        WCHK.append((2 + i, j + 1, int((g > m.reindex(g.index)).sum())))
ws.write(3 + len(ALL), 0, "窓の数")
for j, s in enumerate(WSETS):
    ws.write_formula(3 + len(ALL), j + 1, f'=COUNTIFS(\'10年窓\'!$A$2:$A${NW},"{s}",\'10年窓\'!$B$2:$B${NW},"MPI(ver4.0)")')
ws.write(5 + len(ALL), 0, "Pythonとの最大|差|", F["b"])
ws.write_formula(5 + len(ALL), 1, "=MAX(" + ",".join(f"ABS({CN(c)}{rr + 1}-{v})" for rr, c, v in WCHK) + ")")
WROW = 6 + len(ALL)

# ------------------------------------------------------------------ 数式検算: 12か月線のシグナルを日次生データから
DN = pd.read_pickle("data/daily_NDX.pkl"); ND = len(DN) + 1
ws = wb.add_worksheet("検算_12か月線")
hdr(ws, 0, ["日付", "高値", "安値", "終値", "月末(数式)", "月末累計(数式)", "足番号(数式)"])
ws.set_column(0, 0, 11); ws.set_column(1, 6, 10)
for i, (dt_, x) in enumerate(DN.iterrows()):
    r_ = i + 2
    ws.write_datetime(i + 1, 0, dt_.to_pydatetime(), F["d"])
    ws.write_number(i + 1, 1, x.h); ws.write_number(i + 1, 2, x.l); ws.write_number(i + 1, 3, x.c)
    ws.write_formula(i + 1, 4, f"=IF(MONTH(A{r_ + 1})<>MONTH(A{r_}),1,0)" if i < len(DN) - 1 else "=1")
    ws.write_formula(i + 1, 5, f"=E{r_}" if i == 0 else f"=F{r_ - 1}+E{r_}")
    ws.write_formula(i + 1, 6, "=0" if i == 0 else f"=F{r_ - 1}")      # k=0: 足番号 = 前日までの月末の数
sig12 = O["sig"][("NDX", 0, "12か月線")]
NB = len(sig12)
bc = ["足#", "月(Py)", "終値(数式)", "締め日(数式)", "12か月平均(数式)", "状態(数式)", "前の状態(数式)", "シグナル(数式)", "シグナル(Py)", "一致"]
c0 = 8; hdr(ws, 0, bc, c0)
col = {n: CN(c0 + j) for j, n in enumerate(bc)}
G = f"$G$2:$G${ND}"
for j in range(NB):
    r_ = j + 2; p = r_ - 1
    ws.write_number(j + 1, c0, j); ws.write(j + 1, c0 + 1, str(sig12.index[j]))
    last = f'COUNTIF({G},"<="&{col["足#"]}{r_})'
    ws.write_formula(j + 1, c0 + 2, f"=INDEX($D$2:$D${ND},{last})")
    ws.write_formula(j + 1, c0 + 3, f"=INDEX($A$2:$A${ND},{last})", F["d"])
    cC = col["終値(数式)"]
    if j >= 11:
        ws.write_formula(j + 1, c0 + 4, f"=AVERAGE({cC}{r_ - 11}:{cC}{r_})")
        ws.write_formula(j + 1, c0 + 5, f"=IF({cC}{r_}>{col['12か月平均(数式)']}{r_},1,0)")
    else:
        ws.write(j + 1, c0 + 5, "")
    ws.write_formula(j + 1, c0 + 6, "=0" if j == 0 else f'=IF({col["状態(数式)"]}{p}="",{col["前の状態(数式)"]}{p},{col["状態(数式)"]}{p})')
    st, pv = f'{col["状態(数式)"]}{r_}', f'{col["前の状態(数式)"]}{r_}'
    ws.write_formula(j + 1, c0 + 7, f'=IF({st}="",0,IF({st}<>{pv},IF({st}=1,1,-1),0))')
    ws.write_number(j + 1, c0 + 8, int(sig12.sig.iloc[j]))
    ws.write_formula(j + 1, c0 + 9, f"=IF({col['シグナル(数式)']}{r_}={col['シグナル(Py)']}{r_},1,0)")
NBr = NB + 1
sc = c0 + len(bc) + 1
ws.write(1, sc, "シグナル不一致数(数式)", F["b"]); ws.write_formula(1, sc + 1, f"=COUNT({col['足#']}2:{col['足#']}{NBr})-SUM({col['一致']}2:{col['一致']}{NBr})")
ws.write(2, sc, "シグナル本数(数式)"); ws.write_formula(2, sc + 1, f'=COUNTIF({col["シグナル(数式)"]}2:{col["シグナル(数式)"]}{NBr},"<>0")')
for j in range(NB):
    ws.write_number(j + 1, sc + 3, float(sig12.c.iloc[j]))
ws.write(0, sc + 3, "終値(Py)", F["h"])
ws.write(3, sc, "終値の最大|差|", F["b"])
ws.write_array_formula(3, sc + 1, 3, sc + 1, f"{{=MAX(ABS({col['終値(数式)']}2:{col['終値(数式)']}{NBr}-{CN(sc + 3)}2:{CN(sc + 3)}{NBr}))}}")
ws.freeze_panes(1, 1)
SNAME = "検算_12か月線"

# ------------------------------------------------------------------ 数式検算: 100万円一括の日次台帳（12か月線、NDX 1989-2026、税・手数料・為替なし）
c3 = COST["NDX"][0]
cfgL = Cfg(name="ledger", lev_cost=c3, financing=True, one_er=0.0015, dividends=True, exec_lag=1, contrib_at_month_end=False,
           tax_on=False, infl_adj=False, start="1989-01", end=END, initial=INITIAL, monthly=0.0)
rL, hL = run_rule(DN, sig12, cfgL)
dd = DN.loc["1989-01-01":"2026-10-31"]
off = DN.index.get_loc(dd.index[0])          # 検算_12か月線 の行 = off + 2 + i
ws = wb.add_worksheet("検算_台帳_一括")
LC = ["日付", "r(数式)", "暦日数", "米3M金利", "1倍配当(日)", "3倍日次(数式)", "1倍日次(数式)", "月初(数式)", "約定シグナル(数式)",
      "3倍 成長後", "1倍 成長後(配当込)", "売実行", "買実行", "状態(1=保有)", "現金 約定後", "3倍 約定後", "1倍 約定後", "振替額",
      "振替実行", "3倍 期末", "1倍 期末", "現金 期末", "総資産(数式)", "総資産(Python)", "乖離率(数式)", "投入額(数式)"]
hdr(ws, 0, LC); ws.set_column(0, 0, 11); ws.set_column(1, 25, 12)
prm = [("c3(3倍コスト)", c3), ("1倍経費率", 0.0015), ("毎月の積立", 0.0), ("振替率", 0.01), ("初期投資(円)", INITIAL)]
for i, (t, v) in enumerate(prm):
    ws.write(i, 27, t); ws.write_number(i, 28, v)
# 開始時の状態 = 開始前日（1988/12末）が属する足の『状態』（数式）
sr0 = off + 1     # 開始前日の行（1始まり）= off+1
ws.write(5, 27, "開始時の状態(数式)", F["b"])
ws.write_formula(5, 28, f"=INDEX({SNAME}!${col['前の状態(数式)']}$2:${col['前の状態(数式)']}${NBr},{SNAME}!G{sr0 + 1}+1)")
ws.write(6, 27, "開始時の状態(Python)"); ws.write(6, 28, init_regime(sig12, "1989-01"))
SIGC = col["シグナル(数式)"]
for i, (dt_, x) in enumerate(dd.iterrows()):
    r_ = i + 2; p = r_ - 1; sr = off + 2 + i
    ws.write_formula(i + 1, 0, f"={SNAME}!A{sr}", F["d"])
    ws.write_formula(i + 1, 1, f"={SNAME}!D{sr}/{SNAME}!D{sr - 1}-1")
    ws.write_number(i + 1, 2, x["dt"]); ws.write_number(i + 1, 3, x["rf"]); ws.write_number(i + 1, 4, x["dy"])
    ws.write_formula(i + 1, 5, f"=3*(B{r_}+E{r_})-2*D{r_}*C{r_}/365-$AC$1*C{r_}/365")
    ws.write_formula(i + 1, 6, f"=B{r_}-$AC$2*C{r_}/365")
    ws.write_formula(i + 1, 7, "=1" if i == 0 else f"=IF(MONTH(A{r_})<>MONTH(A{p}),1,0)")
    ws.write_formula(i + 1, 8, "=0" if i == 0 else
                     f"=IF({SNAME}!G{sr}<>{SNAME}!G{sr - 1},INDEX({SNAME}!${SIGC}$2:${SIGC}${NBr},{SNAME}!G{sr - 1}+1),0)")
    pv = (lambda c: "0") if i == 0 else (lambda c: f"{c}{p}")
    regprev = "$AC$6" if i == 0 else f"N{p}"
    ws.write_formula(i + 1, 9, f"={pv('T')}*(1+F{r_})")
    ws.write_formula(i + 1, 10, f"={pv('U')}*(1+G{r_})*(1+E{r_})")
    ws.write_formula(i + 1, 11, f"=AND(I{r_}=-1,{regprev}=1)")
    ws.write_formula(i + 1, 12, f"=AND(I{r_}=1,{regprev}=0)")
    ws.write_formula(i + 1, 13, f"=IF(L{r_},0,IF(M{r_},1,{regprev}))")
    ws.write_formula(i + 1, 14, f"=IF(L{r_},{pv('V')}+J{r_},IF(M{r_},0,{pv('V')}))")
    ws.write_formula(i + 1, 15, f"=IF(L{r_},0,IF(M{r_},J{r_}+{pv('V')}+K{r_},J{r_}))")
    ws.write_formula(i + 1, 16, f"=IF(M{r_},0,K{r_})")
    ws.write_formula(i + 1, 17, f"=IF(L{r_},O{r_}*$AC$4,{pv('R')})")
    ws.write_formula(i + 1, 25, f"=IF(H{r_}=1,$AC$3,0)" + ("+$AC$5" if i == 0 else ""))
    ws.write_formula(i + 1, 18, f"=IF(AND(H{r_}=1,N{r_}=0,O{r_}>0),MIN(R{r_},O{r_}),0)")
    ws.write_formula(i + 1, 19, f"=P{r_}+IF(N{r_}=1,Z{r_},0)")
    ws.write_formula(i + 1, 20, f"=Q{r_}+IF(N{r_}=0,Z{r_},0)+S{r_}")
    ws.write_formula(i + 1, 21, f"=O{r_}-S{r_}")
    ws.write_formula(i + 1, 22, f"=T{r_}+U{r_}+V{r_}", F["yen"])
    ws.write_number(i + 1, 23, hL.value_ccy.iloc[i], F["yen"])
    ws.write_formula(i + 1, 24, f"=W{r_}/X{r_}-1", F["sci"])
NL = len(dd) + 1
ws.write(8, 27, "最大|乖離率|", F["b"]); ws.write_array_formula(8, 28, 8, 28, f"{{=MAX(ABS(Y2:Y{NL}))}}", F["sci"])
ws.write(9, 27, "最終(数式)"); ws.write_formula(9, 28, f"=W{NL}", F["yen"])
ws.write(10, 27, "最終(Python)"); ws.write_number(10, 28, rL["final_pre_liq"], F["yen"])
ws.write(11, 27, "約定シグナル数(数式)"); ws.write_formula(11, 28, f'=COUNTIF(I2:I{NL},"<>0")')
ws.write(12, 27, "約定シグナル数(Py)"); ws.write_number(12, 28, sum(1 for d_ in exec_of(sig12) if dd.index[0] <= d_ < dd.index[-1]))
ws.freeze_panes(1, 1)
wb.close()
pd.to_pickle(dict(SUMROW=SUMROW, WROW=WROW, sc=sc, n_dec={m: sum(DEC[(m, s)] for s in SETORDER) for m in MODEL}), "data/simple_report.pkl")
print("excel ok")

# ================================================================= グラフ
SHORT = {"NDX 1989-2026": "NDX\n1989-2026\n【IS】", "S&P500 1950-1985": "S&P500\n1950-1985", "NASDAQ総合 1974-1985": "NASDAQ総合\n1974-1985",
         "NDX 2022/9-2026": "NDX\n2022/9-2026", "S&P500 1985-2026": "S&P500\n1985-2026", "ダウ 1995-2026": "ダウ\n1995-2026",
         "ラッセル2000 1991-2026": "ラッセル2000\n1991-2026"}
LM = "一括100万"


def okuman(x, _=None):
    return f"{x / 1e8:,.0f}億" if x >= 1e8 else f"{x / 1e4:,.0f}万"


# fig11: NDX IS、100万円一括、締め日21通りの分布
g = R[(R["mode"] == LM) & (R.set == SETORDER[0])]
fig, ax = plt.subplots(figsize=(11.5, 5.8), dpi=110)
for yi, ru in enumerate(ALL):
    y = len(ALL) - 1 - yi
    x = g[g.rule == ru]
    col_ = ORANGE if ru == "MPI(ver4.0)" else (BLUE if ru in RULES else GRAY)
    if ru in RULES:
        jit = (np.random.default_rng(3).random(len(x)) - 0.5) * 0.3
        ax.scatter(x.final, y + jit, s=26, color=col_, alpha=0.6, edgecolor="white", lw=0.5, zorder=3)
        m = x.final.median()
        ax.plot([m, m], [y - 0.32, y + 0.32], color=INK, lw=2.2, zorder=4)
        ax.text(9e9, y, f"中央値 {okuman(m)}円（{okuman(x.final.min())}〜{okuman(x.final.max())}）", va="center", fontsize=8.5, color=INK2)
    else:
        ax.scatter(x.final, [y], marker="s", s=60, color=col_, edgecolor=INK, lw=0.8, zorder=3)
        ax.text(9e9, y, f"{okuman(x.final.iloc[0])}円（最大DD {x.mdd.iloc[0]:.0%}）", va="center", fontsize=8.5, color=INK2)
mpi_med = g[g.rule == "MPI(ver4.0)"].final.median()
ax.axvline(mpi_med, color=ORANGE, lw=1, ls="--", zorder=1)
ax.set_xscale("log"); ax.set_xlim(5e6, 1.2e11)
ax.xaxis.set_major_formatter(mt.FuncFormatter(okuman))
ax.set_yticks(range(len(ALL))[::-1]); ax.set_yticklabels(ALL, fontsize=9.5)
for t in ax.get_yticklabels():
    if t.get_text() == "MPI(ver4.0)": t.set_fontweight("bold")
ax.grid(axis="x", alpha=0.25); ax.set_xlabel("税引後最終資産（円、対数目盛）　点=締め日21通り、黒線=中央値、破線=MPIの中央値")
ax.set_title("100万円一括（NDX 1989/1〜2026/10）：12か月線・12か月モメンタムの中央値はMPIの約2倍",
             loc="left", fontsize=12, fontweight="bold")
fig.text(0.01, 0.01, "現実コストC・税引後。運用の仕組みは全ルール共通（買い=全額3倍、売り=現金→毎月1%ずつ1倍）。灰色の四角=3倍保有・1倍保有（締め日に依存しない）",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT / "fig11_単純ルール_NDX.png"); plt.close()

# fig12: 全セット ヒートマップ（中央値 ÷ MPI中央値）
rows12 = ALL[1:]
M = np.array([[MED[(LM, s, ru)] / MED[(LM, s, "MPI(ver4.0)")] for s in SETORDER] for ru in rows12])
L_ = np.log2(M)
cmap = LinearSegmentedColormap.from_list("div", ["#d03b3b", "#f0efec", BLUE])
fig, ax = plt.subplots(figsize=(11.5, 5.6), dpi=110)
im = ax.imshow(np.clip(L_, -2, 2), cmap=cmap, vmin=-2, vmax=2, aspect="auto")
for i, ru in enumerate(rows12):
    for j, s in enumerate(SETORDER):
        v = M[i, j]
        lab_ = f"{v:.2f}倍"
        if ru in RULES:
            lab_ += f"\n勝{PW[(LM, s, ru)]}/21"
        ax.text(j, i, lab_, ha="center", va="center", fontsize=8.5, color="white" if abs(L_[i, j]) > 1.4 else INK)
ax.set_xticks(range(len(SETORDER))); ax.set_xticklabels([SHORT[s] for s in SETORDER], fontsize=9)
ax.set_yticks(range(len(rows12))); ax.set_yticklabels(rows12, fontsize=9.5)
ax.axvline(0.5, color=INK, lw=1.5); ax.axhline(4.5, color=INK, lw=1.2)
ax.tick_params(length=0); [s_.set_visible(False) for s_ in ax.spines.values()]
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, ticks=[-2, -1, 0, 1, 2])
cb.ax.set_yticklabels(["1/4倍", "1/2倍", "同じ", "2倍", "4倍"]); cb.set_label("MPIの中央値に対する倍率", fontsize=8.5)
ax.set_title("100万円一括：12か月線は全7セットでMPIを上回る（青=MPIより良い、赤=悪い）", loc="left", fontsize=12, fontweight="bold")
fig.text(0.01, 0.01, "各セルは締め日21通りの税引後最終資産の中央値 ÷ MPIの中央値。『勝n/21』=同じ締め日でMPIを上回った数。下2行(3倍保有・1倍保有)は締め日に依存しない参考",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT / "fig12_単純ルール_全セット.png"); plt.close()

# fig13: NDX 締め日k=0 の資産推移（100万円一括）
P_ = O["paths"]
fig, ax = plt.subplots(figsize=(11.5, 5.6), dpi=110)
spec = [("MPI(ver4.0)", ORANGE, "-"), ("12か月線", BLUE, "-"), ("3倍保有", INK2, "--"), ("1倍保有", GRAY, "-")]
labs = []
for ru, c_, ls in spec:
    v = P_[ru]
    ax.plot(v.index, v.values, color=c_, lw=2, ls=ls)
    fin = R[(R["mode"] == LM) & (R.set == SETORDER[0]) & (R.rule == ru) & (R.k == 0)].final.iloc[0]
    labs.append([np.log10(v.values[-1]), f"{ru}  {okuman(fin)}円", c_])
labs.sort(key=lambda z: -z[0])
for i in range(1, len(labs)):                       # ラベルが重ならないよう対数で最小0.28ずつ離す
    labs[i][0] = min(labs[i][0], labs[i - 1][0] - 0.28)
for y_, t_, c_ in labs:
    ax.text(pd.Timestamp("2027-03-01"), 10 ** y_, t_, va="center", fontsize=8.5, color=INK)
    ax.plot([pd.Timestamp("2026-11-15"), pd.Timestamp("2027-02-01")], [10 ** y_] * 2, color=c_, lw=2)
ax.set_yscale("log"); ax.yaxis.set_major_formatter(mt.FuncFormatter(okuman)); ax.set_ylim(1e5, 1e10)
ax.set_xlim(pd.Timestamp("1988-06-01"), pd.Timestamp("2033-06-01"))
ax.grid(alpha=0.25)
for d_, t_ in [("2000-03-01", "ITバブル崩壊"), ("2008-09-01", "リーマン"), ("2020-03-01", "コロナ")]:
    ax.axvline(pd.Timestamp(d_), color=INK2, lw=0.6, ls=":")
    ax.text(pd.Timestamp(d_), 6e9, t_, fontsize=8, color=INK2, ha="center")
ax.set_title("100万円一括の資産推移（NDX、月末締め）：3倍保有は2002年に99%以上を失う。売買ルールの価値はこの回避", loc="left",
             fontsize=11.5, fontweight="bold")
fig.text(0.01, 0.01, "円建て評価額（税引前、右端の金額は清算後の税引後）。現実コストC。締め日k=0（月末）は21通りの1つにすぎない点に注意", fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT / "fig13_単純ルール_資産推移.png"); plt.close()
print("charts ok")
