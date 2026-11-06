"""シグナル摂動テストの Excel（数式で突合）とグラフ。前提: python3 perturb.py 実行済み"""
import sys
sys.path.insert(0, ".")
from perturb import *
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name as CN
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.ticker as mt
from matplotlib import font_manager

OUT = Path("./out"); OUT.mkdir(exist_ok=True)
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams.update({"font.family": "IPAGothic", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, AQUA, GRAY, INK, INK2 = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984", "#0b0b0b", "#52514e"

P = pd.read_pickle("data/perturb.pkl"); R = P["res"]; EP = P["ep"]; COST = P["cost"]
SETORDER = [s[0] for s in SETS]; KIND = {s[0]: s[1] for s in SETS}
KV = [f"k{k:+d}" for k in KS]; DV = [f"d{x}" for x in CAL_DAYS]
REF = R[R.test == "参考"].pivot(index="set", columns="var", values="final")
P1 = R[R.test == "P1締め日"]; P2 = R[R.test == "P2約定遅延"]

# Python 側の集計（Excel と突合する）
SUM = []
for s in SETORDER:
    g = P1[(P1.set == s) & P1["var"].isin(KV)]
    f = g.final.values; b = g[g["var"] == "k+0"].final.iloc[0]
    SUM.append(dict(set=s, base=b, med=np.median(f), mn=f.min(), mx=f.max(), n=len(f),
                    w3=int((f > REF.loc[s, "3倍単純積立"]).sum()), w1=int((f > REF.loc[s, "1倍単純積立"]).sum()),
                    above=int((f > b).sum())))
SUM = pd.DataFrame(SUM).set_index("set")

wb = xlsxwriter.Workbook(str(OUT / "MPI_ver4_摂動テスト.xlsx"), {"use_future_functions": True})
F = dict(h=wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True, "valign": "top", "border": 1}),
         yen=wb.add_format({"num_format": "#,##0"}), oku=wb.add_format({"num_format": "#,##0.00"}), x2=wb.add_format({"num_format": "0.00"}),
         pct=wb.add_format({"num_format": "0.0%"}), f6=wb.add_format({"num_format": "0.000000"}), sci=wb.add_format({"num_format": "0.00E+00"}),
         title=wb.add_format({"bold": True, "font_size": 14}), b=wb.add_format({"bold": True}),
         wrap=wb.add_format({"text_wrap": True, "valign": "top"}), d=wb.add_format({"num_format": "yyyy-mm-dd"}),
         sel=wb.add_format({"bold": True, "bg_color": "#FFF2CC"}))


def hdr(ws, r, cols, c0=0):
    for j, x in enumerate(cols):
        ws.write(r, c0 + j, x, F["h"])


# ------------------------------------------------------------------ 概要
ws = wb.add_worksheet("概要")
ws.set_column(0, 0, 34); ws.set_column(1, 8, 14)
ws.write(0, 0, "シグナル摂動テスト：月足の締め日・約定日・個別シグナルを動かしたときの ver4.0", F["title"])
ws.write(1, 0, "現実コストC（SBI手数料・為替・日本税制・較正コスト）、名目3万円/月、税引後。積立日・コストは固定し、シグナルだけを動かす。数式は「P1データ」シートを集計")
hdr(ws, 3, ["項目 \\ 検証セット"] + SETORDER)
ws.write(4, 0, "区分"); [ws.write(4, j + 1, KIND[s]) for j, s in enumerate(SETORDER)]
NP1 = len(P1) + 1
lab = ["基準 k=0（億円）", "締め日21通りの中央値（億円, 数式）", "最小（億円, 数式）", "最大（億円, 数式）",
       "中央値 ÷ 基準（判定A, 数式）", "最小 ÷ 基準（数式）", "最大 ÷ 基準（数式）",
       "3倍単純積立（億円）", "1倍単純積立（億円）", "3倍積立に勝つ通り数 /21（判定B, 数式）", "1倍積立に勝つ通り数 /21（数式）",
       "基準より良い通り数 /20（数式）"]
for i, t in enumerate(lab):
    ws.write(5 + i, 0, t, F["b"] if "判定" in t else None)
for j, s in enumerate(SETORDER):
    c = CN(j + 1)
    cond = f'P1データ!$A$2:$A${NP1}=$' + c + '$4'  # 配列条件
    rng = f"P1データ!$E$2:$E${NP1}"
    kc = f"(P1データ!$C$2:$C${NP1}=\"k\")"
    ws.write_formula(5, j + 1, f'=SUMIFS(P1データ!$E$2:$E${NP1},P1データ!$A$2:$A${NP1},{c}$4,P1データ!$B$2:$B${NP1},"k+0")/1E8', F["oku"])
    ws.write_array_formula(6, j + 1, 6, j + 1, f"{{=MEDIAN(IF(({cond})*{kc},{rng}))/1E8}}", F["oku"])
    ws.write_array_formula(7, j + 1, 7, j + 1, f"{{=MIN(IF(({cond})*{kc},{rng}))/1E8}}", F["oku"])
    ws.write_array_formula(8, j + 1, 8, j + 1, f"{{=MAX(IF(({cond})*{kc},{rng}))/1E8}}", F["oku"])
    for r_, src in ((9, 7), (10, 8), (11, 9)):
        ws.write_formula(r_, j + 1, f"={c}{src}/{c}$6", F["x2"])
    ws.write_number(12, j + 1, REF.loc[s, "3倍単純積立"] / 1e8, F["oku"]); ws.write_number(13, j + 1, REF.loc[s, "1倍単純積立"] / 1e8, F["oku"])
    ws.write_formula(14, j + 1, f'=COUNTIFS(P1データ!$A$2:$A${NP1},{c}$4,P1データ!$C$2:$C${NP1},"k",P1データ!$I$2:$I${NP1},">1")')
    ws.write_formula(15, j + 1, f'=COUNTIFS(P1データ!$A$2:$A${NP1},{c}$4,P1データ!$C$2:$C${NP1},"k",P1データ!$J$2:$J${NP1},">1")')
    ws.write_formula(16, j + 1, f'=COUNTIFS(P1データ!$A$2:$A${NP1},{c}$4,P1データ!$C$2:$C${NP1},"k",P1データ!$H$2:$H${NP1},">1")')
ws.write(18, 0, "Python との差（突合）", F["b"])
hdr(ws, 19, ["項目"] + SETORDER)
chk = [("中央値の差(円)", 6, "med", 1e8), ("最小の差(円)", 7, "mn", 1e8), ("最大の差(円)", 8, "mx", 1e8),
       ("3倍積立に勝つ数の差", 14, "w3", 1), ("1倍積立に勝つ数の差", 15, "w1", 1), ("基準より良い数の差", 16, "above", 1)]
for i, (t, rr, key, sc) in enumerate(chk):
    ws.write(20 + i, 0, t)
    for j, s in enumerate(SETORDER):
        c = CN(j + 1)
        ws.write_formula(20 + i, j + 1, f"={c}{rr + 1}*{sc}-{float(SUM.loc[s, key])!r}", F["sci"])
ws.write(27, 0, "最大|差|", F["b"]); ws.write_array_formula(27, 1, 27, 1, "{=MAX(ABS(B21:H26))}", F["sci"])
ws.freeze_panes(5, 1)

# ------------------------------------------------------------------ 設計
ws = wb.add_worksheet("検証設計")
ws.set_column(0, 0, 24); ws.set_column(1, 1, 120)
rows_ = [("項目", "内容"),
         ("目的", "ver4.0 の結果が「月足の締め日」「約定日」「少数のシグナル」にどれだけ依存しているかを測る（前回の検証で残った最大の疑問）"),
         ("共通の条件", "現実コストC、名目3万円/月、積立は月初。積立日・コスト・税は固定し、シグナルだけを動かす。基準(k=0)=ケースC 38.0億円"),
         ("P1 締め日シフト", "月足の締め日を『月末最終営業日 + k 営業日』に変え、全期間の月足・MACD(12,26,9)・パラボリック(0.02,0.02,0.2)を作り直す。k=-10〜+10 の21通り(≒1か月の全位相)。シグナルは締め日の翌営業日の引けで約定。参考で暦日締め(5/10/15/20/25日)も計算"),
         ("P2 約定遅延", "シグナルは基準のまま、約定を締め日の d 営業日後に(d=0〜5、d=1が基準、d=0 は厳密には実行不能)"),
         ("P3 エピソード除去", "NDX(IS)の基準シグナル25本のうち連続する2本(買→売=保有1回、売→買=退避1回)を1組ずつ消す。『その1回がなかったら』で各シグナルの寄与を測る"),
         ("検証セット", "IS: NDX 1985/10〜2026/10。OOS: S&P500 1950-85、NASDAQ総合 1974-85、NDX 2022/9-26、S&P500 1985-26、ダウ 1995-26、ラッセル2000 1991-26（前回のOOS検証と同一）"),
         ("判定A（事前固定）", "P1の21通りの中央値 ÷ 基準。0.5以上=頑健、0.25〜0.5=中程度、0.25未満=脆弱（基準が『当たりの締め日』だった）"),
         ("判定B（事前固定）", "P1の21通りのうち 3倍単純積立・1倍単純積立 に勝つ割合。80%以上で『締め日に依らず優位』"),
         ("判定C（事前固定）", "P3で1組除去しただけで最終資産が半分以下になる組があれば『単一シグナル依存』"),
         ("注意", "21通りは隣どうしで月足の大半を共有するので独立な試行ではない（割合は記述統計で、有意性検定ではない）"),
         ]
for i, rr in enumerate(rows_):
    for j, x in enumerate(rr):
        ws.write(i, j, x, F["h"] if i == 0 else F["wrap"])

# ------------------------------------------------------------------ P1データ
ws = wb.add_worksheet("P1データ")
hdr(ws, 0, ["セット", "締め日", "種類", "シグナル数", "税引後最終資産(円)", "投入元本(円)", "最大DD", "基準比(数式)",
            "3倍積立比(数式)", "1倍積立比(数式)", "3倍単純積立(円)", "1倍単純積立(円)", "基準k=0(円)"])
ws.set_column(0, 0, 20); ws.set_column(1, 12, 13)
for i, x in enumerate(P1.itertuples(), start=1):
    r_ = i + 1
    ws.write(i, 0, x.set); ws.write(i, 1, x.var); ws.write(i, 2, x.var[0]); ws.write_number(i, 3, x.n_sig)
    ws.write_number(i, 4, x.final, F["yen"]); ws.write_number(i, 5, x.contrib, F["yen"]); ws.write_number(i, 6, x.mdd, F["pct"])
    ws.write_formula(i, 7, f"=E{r_}/M{r_}", F["x2"]); ws.write_formula(i, 8, f"=E{r_}/K{r_}", F["x2"]); ws.write_formula(i, 9, f"=E{r_}/L{r_}", F["x2"])
    ws.write_number(i, 10, REF.loc[x.set, "3倍単純積立"], F["yen"]); ws.write_number(i, 11, REF.loc[x.set, "1倍単純積立"], F["yen"])
    ws.write_formula(i, 12, f'=SUMIFS($E$2:$E${NP1},$A$2:$A${NP1},A{r_},$B$2:$B${NP1},"k+0")', F["yen"])
ws.autofilter(0, 0, NP1 - 1, 12); ws.freeze_panes(1, 2)

# ------------------------------------------------------------------ P2
ws = wb.add_worksheet("P2約定遅延")
hdr(ws, 0, ["約定 \\ 検証セット"] + SETORDER); ws.set_column(0, 0, 30); ws.set_column(1, 7, 14)
ws.write(1, 0, "税引後最終資産(円)", F["b"])
for i, lg in enumerate(LAGS):
    ws.write(2 + i, 0, f"締め日の{lg}営業日後の引け" + ("（基準）" if lg == 1 else "（実行不能・参考）" if lg == 0 else ""))
    for j, s in enumerate(SETORDER):
        ws.write_number(2 + i, j + 1, P2[(P2.set == s) & (P2["var"] == f"lag{lg}")].final.iloc[0], F["yen"])
r0 = 3 + len(LAGS)
ws.write(r0, 0, "基準(1営業日後)比（数式）", F["b"])
for i, lg in enumerate(LAGS):
    ws.write(r0 + 1 + i, 0, f"{lg}営業日後")
    for j in range(len(SETORDER)):
        c = CN(j + 1); ws.write_formula(r0 + 1 + i, j + 1, f"={c}{3 + i}/{c}$4-1", F["pct"])

# ------------------------------------------------------------------ P3
ws = wb.add_worksheet("P3エピソード除去")
hdr(ws, 0, ["#", "消すシグナル1", "種類1", "消すシグナル2", "種類2", "意味", "除去後の最終資産(円)", "基準(円)", "基準比(数式)", "対数比(数式)", "半分以下(数式)"])
ws.set_column(0, 0, 4); ws.set_column(1, 4, 12); ws.set_column(5, 5, 22); ws.set_column(6, 10, 15)
for i, x in enumerate(EP.itertuples(), start=1):
    r_ = i + 1
    ws.write_number(i, 0, i); ws.write_datetime(i, 1, x.d1.to_pydatetime(), F["d"]); ws.write(i, 2, "買" if x.s1 == 1 else "売")
    if pd.notna(x.d2):
        ws.write_datetime(i, 3, x.d2.to_pydatetime(), F["d"]); ws.write(i, 4, "買" if x.s2 == 1 else "売")
    ws.write(i, 5, x.kind); ws.write_number(i, 6, x.final, F["yen"]); ws.write_number(i, 7, P["base"], F["yen"])
    ws.write_formula(i, 8, f"=G{r_}/H{r_}", F["x2"]); ws.write_formula(i, 9, f"=LN(I{r_})", F["f6"])
    ws.write_formula(i, 10, f'=IF(J{r_}<=-LN(2),"○","")')
NE = len(EP) + 1
ws.write(NE + 1, 5, "半分以下になる組の数(数式)", F["b"]); ws.write_formula(NE + 1, 6, f'=COUNTIF(K2:K{NE},"○")')
ws.write(NE + 2, 5, "Python"); ws.write_number(NE + 2, 6, int((EP.dlog <= -np.log(2)).sum()))
ws.write(NE + 3, 5, "退避12回のうち役立った回数(数式)", F["b"])
ws.write_formula(NE + 3, 6, f'=COUNTIFS(F2:F{NE},"退避を消す(保有継続)",I2:I{NE},"<1")')
ws.write(NE + 4, 5, "Python"); ws.write_number(NE + 4, 6, int(((EP.kind == "退避を消す(保有継続)") & (EP.dlog < 0)).sum()))
ws.write(NE + 5, 5, "最大|対数比の差|(数式)", F["b"])
ws.write_array_formula(NE + 5, 6, NE + 5, 6, "{=MAX(ABS(J2:J%d-%s))}" % (NE, "{" + ";".join(repr(float(v)) for v in EP.dlog) + "}"), F["sci"])
ws.freeze_panes(1, 0)


# ------------------------------------------------------------------ 数式検算: 締め日シフトの月足→MACD→パラボリック→シグナルを日次生データから
DN = pd.read_pickle("data/daily_NDX.pkl")
ND = len(DN) + 1


def shift_sheet(k):
    name = f"検算_締め日{k:+d}"
    ws = wb.add_worksheet(name)
    bars = P["bars"][("NDX", f"k{k:+d}")]; sg = P["sigs"][("NDX", f"k{k:+d}")]
    hdr(ws, 0, ["日付", "始値", "高値", "安値", "終値", "月末(数式)", "月末累計(数式)", "足番号(数式)"])
    ws.set_column(0, 0, 11); ws.set_column(1, 7, 10)
    ws.write(0, 9, "k(営業日)"); ws.write_number(0, 10, k)
    for i, (dt_, x) in enumerate(DN.iterrows()):
        r_ = i + 2
        ws.write_datetime(i + 1, 0, dt_.to_pydatetime(), F["d"])
        for j, col in enumerate("ohlc"):
            ws.write_number(i + 1, 1 + j, x[col])
        ws.write_formula(i + 1, 5, f"=IF(MONTH(A{r_ + 1})<>MONTH(A{r_}),1,0)" if i < len(DN) - 1 else "=1")
        ws.write_formula(i + 1, 6, f"=F{r_}" if i == 0 else f"=G{r_ - 1}+F{r_}")
        # 足番号 = 位置 (i-k-1) までの月末の数
        ws.write_formula(i + 1, 7, f"=IF({i}-$K$1-1<0,0,INDEX($G$2:$G${ND},MIN({i}-$K$1,{len(DN)})))")
    # 月足とインジケーター（列 M 以降）
    c0 = 12
    cols = ["足#", "月(Py)", "始値", "高値", "安値", "終値", "締め日", "EMA12", "EMA26", "MACD", "シグナル9",
            # PSAR
            "BL0", "MM0", "R0", "AC0", "Ra", "反転", "BL1", "Rb", "MM1", "AC1", "初回", "延長", "MM", "AC", "PSAR",
            # シグナル
            "有効", "xo", "xu", "買条件", "売条件", "LS前", "PS前", "買発生", "LSa", "PSa", "売発生", "LS", "PS", "シグナル(数式)",
            "シグナル(Py)", "一致", "PSAR(Py)", "PSAR差", "高値差", "安値差", "終値差"]
    hdr(ws, 0, cols, c0)
    col = {n: CN(c0 + j) for j, n in enumerate(cols)}
    NB = len(bars)
    H = f"$H$2:$H${ND}"
    for j in range(NB):
        r_ = j + 2; p = r_ - 1; pp = r_ - 2
        X = lambda n, rr=r_: f"{col[n]}{rr}"
        w = lambda n, f, fm=None: ws.write_formula(j + 1, c0 + cols.index(n), f, fm)
        ws.write_number(j + 1, c0, j); ws.write(j + 1, c0 + 1, str(bars.index[j]))
        first = f"(COUNTIF({H},\"<\"&{X('足#')})+1)"; last = f"COUNTIF({H},\"<=\"&{X('足#')})"
        w("始値", f"=INDEX($B$2:$B${ND},{first})"); w("高値", f"=MAXIFS($C$2:$C${ND},{H},{X('足#')})")
        w("安値", f"=MINIFS($D$2:$D${ND},{H},{X('足#')})"); w("終値", f"=INDEX($E$2:$E${ND},{last})")
        w("締め日", f"=INDEX($A$2:$A${ND},{last})", F["d"])
        cC, cH, cL = col["終値"], col["高値"], col["安値"]
        if j == 11: w("EMA12", f"=AVERAGE({cC}2:{cC}13)")
        elif j > 11: w("EMA12", f"=2/13*{cC}{r_}+(1-2/13)*{col['EMA12']}{p}")
        if j == 25: w("EMA26", f"=AVERAGE({cC}2:{cC}27)")
        elif j > 25: w("EMA26", f"=2/27*{cC}{r_}+(1-2/27)*{col['EMA26']}{p}")
        if j >= 25: w("MACD", f"={X('EMA12')}-{X('EMA26')}")
        if j == 33: w("シグナル9", f"=AVERAGE({col['MACD']}27:{col['MACD']}35)")
        elif j > 33: w("シグナル9", f"=2/10*{X('MACD')}+(1-2/10)*{col['シグナル9']}{p}")
        if j >= 1:
            init = j == 1
            g = lambda n: f"{col[n]}{p}"
            w("BL0", f"=IF({cC}{r_}>{cC}{p},1,0)" if init else f"={g('BL1')}")
            w("MM0", f"=IF({cC}{r_}>{cC}{p},{cH}{r_},{cL}{r_})" if init else f"={g('MM')}")
            w("R0", f"=IF({cC}{r_}>{cC}{p},{cL}{p},{cH}{p})" if init else f"={g('PSAR')}")
            w("AC0", "=0.02" if init else f"={g('AC')}")
            w("Ra", f"={X('R0')}+{X('AC0')}*({X('MM0')}-{X('R0')})")
            w("反転", f"=IF({X('BL0')}=1,{X('Ra')}>{cL}{r_},{X('Ra')}<{cH}{r_})")
            w("BL1", f"=IF({X('反転')},1-{X('BL0')},{X('BL0')})")
            w("Rb", f"=IF({X('反転')},IF({X('BL0')}=1,MAX({cH}{r_},{X('MM0')}),MIN({cL}{r_},{X('MM0')})),{X('Ra')})")
            w("MM1", f"=IF({X('反転')},IF({X('BL0')}=1,{cL}{r_},{cH}{r_}),{X('MM0')})")
            w("AC1", f"=IF({X('反転')},0.02,{X('AC0')})")
            w("初回", f"=OR({'TRUE' if init else 'FALSE'},{X('反転')})")
            w("延長", f"=AND(NOT({X('初回')}),IF({X('BL1')}=1,{cH}{r_}>{X('MM1')},{cL}{r_}<{X('MM1')}))")
            w("MM", f"=IF({X('延長')},IF({X('BL1')}=1,{cH}{r_},{cL}{r_}),{X('MM1')})")
            w("AC", f"=IF({X('延長')},MIN({X('AC1')}+0.02,0.2),{X('AC1')})")
            lo2 = f",{cL}{pp}" if j > 1 else ""; hi2 = f",{cH}{pp}" if j > 1 else ""
            w("PSAR", f"=IF({X('BL1')}=1,MIN({X('Rb')},{cL}{p}{lo2}),MAX({X('Rb')},{cH}{p}{hi2}))")
        M, S, PS_ = col["MACD"], col["シグナル9"], col["PSAR"]
        if j >= 1:
            w("有効", f"=AND({j}>=34,{j - 1}>=1)")
        else:
            ws.write_boolean(j + 1, c0 + cols.index("有効"), False)
        if j >= 34:
            w("xo", f"=AND({M}{r_}>{S}{r_},{M}{p}<={S}{p})"); w("xu", f"=AND({M}{r_}<{S}{r_},{M}{p}>={S}{p})")
            w("買条件", f"=OR(AND({cL}{r_}>{PS_}{r_},{X('xo')}),AND({M}{r_}>{S}{r_},{cH}{p}<{PS_}{p},{cH}{r_}>{PS_}{r_}))")
            w("売条件", f"=OR(AND({cH}{r_}<{PS_}{r_},{X('xu')}),AND({M}{r_}<{S}{r_},{cL}{p}>{PS_}{p},{cL}{r_}<{PS_}{r_}))")
        else:
            ws.write_boolean(j + 1, c0 + cols.index("買条件"), False); ws.write_boolean(j + 1, c0 + cols.index("売条件"), False)
        w("LS前", "=1" if j == 0 else f"={col['LS']}{p}"); w("PS前", "=1" if j == 0 else f"={col['PS']}{p}")
        w("買発生", f"=AND({X('有効')},{X('LS前')}=1,{X('買条件')})")
        w("LSa", f"=IF({X('買発生')},0,{X('LS前')})"); w("PSa", f"=IF({X('買発生')},1,{X('PS前')})")
        w("売発生", f"=AND({X('有効')},{X('PSa')}=1,{X('売条件')})")
        w("LS", f"=IF({X('売発生')},1,{X('LSa')})"); w("PS", f"=IF({X('売発生')},0,{X('PSa')})")
        w("シグナル(数式)", f"=IF({X('売発生')},-1,IF({X('買発生')},1,0))")
        ws.write_number(j + 1, c0 + cols.index("シグナル(Py)"), int(sg.sig.iloc[j]))
        w("一致", f"=IF({X('シグナル(数式)')}={X('シグナル(Py)')},1,0)")
        if j >= 1:
            ws.write_number(j + 1, c0 + cols.index("PSAR(Py)"), sg.psar.iloc[j])
            w("PSAR差", f"=ABS({X('PSAR')}/{X('PSAR(Py)')}-1)", F["sci"])
        w("高値差", f"=ABS({X('高値')}-{float(bars.h.iloc[j])!r})", F["sci"]); w("安値差", f"=ABS({X('安値')}-{float(bars.l.iloc[j])!r})", F["sci"])
        w("終値差", f"=ABS({X('終値')}-{float(bars.c.iloc[j])!r})", F["sci"])
    NBr = NB + 1
    sc = c0 + len(cols) + 1
    out = [("足の数", f"=COUNT({col['足#']}2:{col['足#']}{NBr})"),
           ("シグナル一致数(数式)", f"=SUM({col['一致']}2:{col['一致']}{NBr})"),
           ("シグナル不一致数(数式)", f"=COUNT({col['足#']}2:{col['足#']}{NBr})-SUM({col['一致']}2:{col['一致']}{NBr})"),
           ("シグナル本数(数式)", f'=COUNTIF({col["シグナル(数式)"]}2:{col["シグナル(数式)"]}{NBr},"<>0")'),
           ("最大|PSAR差|(相対)", f"=MAX({col['PSAR差']}3:{col['PSAR差']}{NBr})"),
           ("最大|高安終値差|", f"=MAX({col['高値差']}2:{col['終値差']}{NBr})")]
    for i, (t, f) in enumerate(out):
        ws.write(i + 2, sc, t, F["b"]); ws.write_formula(i + 2, sc + 1, f, F["sci"] if "差" in t else None)
    ws.freeze_panes(1, 1)
    return name, col, NB


SHIFT_K = [-7, 3]       # P1 の最小(k=-7)と、+側の上位(k=+3)
SH = {k: shift_sheet(k) for k in SHIFT_K}

# ------------------------------------------------------------------ 数式検算: k=-7 の売買台帳（日次、税・手数料・為替なし）を数式だけで
KL = -7
nameS, colS, NBS = SH[KL]
nameS = f"'{nameS}'"   # シート名に +/- を含むので引用符で囲む
c3 = COST["NDX"][0]
cfgL = Cfg(name="ledger", lev_cost=c3, financing=True, one_er=0.0015, dividends=True, exec_lag=1, contrib_at_month_end=False,
           tax_on=False, infl_adj=False, start="1985-10", end=END)
exL = exec_of(P["sigs"][("NDX", f"k{KL:+d}")])
rL, hL, tL = run(DN, DUMMY, cfgL, exec_dates=exL)
dd = DN.loc[:"2026-10-31"]
ws = wb.add_worksheet(f"検算_台帳{KL:+d}")
LC = ["日付", "r(数式)", "暦日数", "米3M金利", "1倍配当(日)", "3倍日次(数式)", "1倍日次(数式)", "月初(数式)", "約定シグナル(数式)",
      "3倍 成長後", "1倍 成長後(配当込)", "売実行", "買実行", "状態(1=保有)", "現金 約定後", "3倍 約定後", "1倍 約定後", "振替額",
      "振替実行", "3倍 期末", "1倍 期末", "現金 期末", "総資産(数式)", "総資産(Python)", "乖離率(数式)"]
hdr(ws, 0, LC); ws.set_column(0, 0, 11); ws.set_column(1, 24, 12)
ws.write(0, 26, "c3(3倍コスト)"); ws.write_number(0, 27, c3, F["f6"])
ws.write(1, 26, "1倍経費率"); ws.write_number(1, 27, 0.0015)
ws.write(2, 26, "積立/月"); ws.write_number(2, 27, 30000)
ws.write(3, 26, "振替率"); ws.write_number(3, 27, 0.01)
SBN = f"{nameS}!$H$2:$H${ND}"; SIGC = colS["シグナル(数式)"]; NBR = NBS + 1
for i, (dt_, x) in enumerate(dd.iterrows()):
    r_ = i + 2; p = r_ - 1
    ws.write_formula(i + 1, 0, f"={nameS}!A{r_}", F["d"])
    ws.write_formula(i + 1, 1, "=0" if i == 0 else f"={nameS}!E{r_}/{nameS}!E{p}-1")
    ws.write_number(i + 1, 2, x["dt"]); ws.write_number(i + 1, 3, x["rf"]); ws.write_number(i + 1, 4, x["dy"])
    ws.write_formula(i + 1, 5, f"=3*(B{r_}+E{r_})-2*D{r_}*C{r_}/365-$AB$1*C{r_}/365")
    ws.write_formula(i + 1, 6, f"=B{r_}-$AB$2*C{r_}/365")
    ws.write_formula(i + 1, 7, "=1" if i == 0 else f"=IF(MONTH(A{r_})<>MONTH(A{p}),1,0)")
    # 前日が締め日（足番号が変わる）なら、その足のシグナルを今日の引けで約定
    ws.write_formula(i + 1, 8, "=0" if i == 0 else
                     f"=IF({nameS}!H{r_}<>{nameS}!H{p},IFERROR(INDEX({nameS}!${SIGC}$2:${SIGC}${NBR},{nameS}!H{p}+1),0),0)")
    pv = (lambda c: "0") if i == 0 else (lambda c: f"{c}{p}")
    ws.write_formula(i + 1, 9, f"={pv('T')}*(1+F{r_})")
    ws.write_formula(i + 1, 10, f"={pv('U')}*(1+G{r_})*(1+E{r_})")
    ws.write_formula(i + 1, 11, f"=AND(I{r_}=-1,{pv('N')}=1)")
    ws.write_formula(i + 1, 12, f"=AND(I{r_}=1,{pv('N')}=0)")
    ws.write_formula(i + 1, 13, f"=IF(L{r_},0,IF(M{r_},1,{pv('N')}))")
    ws.write_formula(i + 1, 14, f"=IF(L{r_},{pv('V')}+J{r_},IF(M{r_},0,{pv('V')}))")
    ws.write_formula(i + 1, 15, f"=IF(L{r_},0,IF(M{r_},J{r_}+{pv('V')}+K{r_},J{r_}))")
    ws.write_formula(i + 1, 16, f"=IF(M{r_},0,K{r_})")
    ws.write_formula(i + 1, 17, f"=IF(L{r_},O{r_}*$AB$4,{pv('R')})")
    ws.write_formula(i + 1, 18, f"=IF(AND(H{r_}=1,N{r_}=0,O{r_}>0),MIN(R{r_},O{r_}),0)")
    ws.write_formula(i + 1, 19, f"=P{r_}+IF(AND(H{r_}=1,N{r_}=1),$AB$3,0)")
    ws.write_formula(i + 1, 20, f"=Q{r_}+IF(AND(H{r_}=1,N{r_}=0),$AB$3,0)+S{r_}")
    ws.write_formula(i + 1, 21, f"=O{r_}-S{r_}")
    ws.write_formula(i + 1, 22, f"=T{r_}+U{r_}+V{r_}", F["yen"])
    ws.write_number(i + 1, 23, hL.value_ccy.iloc[i], F["yen"])
    ws.write_formula(i + 1, 24, f"=IF(X{r_}=0,W{r_},W{r_}/X{r_}-1)", F["sci"])
NL = len(dd) + 1
ws.write(5, 26, "最大|乖離率|", F["b"]); ws.write_array_formula(5, 27, 5, 27, f"{{=MAX(ABS(Y2:Y{NL}))}}", F["sci"])
ws.write(6, 26, "約定シグナル数(数式)"); ws.write_formula(6, 27, f'=COUNTIF(I2:I{NL},"<>0")')
ws.write(7, 26, "期間内シグナル数(Py)"); ws.write_number(7, 27, len(in_period(exL, DN, cfgL)))
ws.write(8, 26, "最終(数式)"); ws.write_formula(8, 27, f"=W{NL}", F["yen"])
ws.write(9, 26, "最終(Python)"); ws.write_number(9, 27, rL["final_pre_liq"], F["yen"])
ws.freeze_panes(1, 1)
wb.close()
pd.to_pickle(dict(SUM=SUM, SH={k: (v[0], v[2]) for k, v in SH.items()}, KL=KL, NL=NL,
                  n_ep_half=int((EP.dlog <= -np.log(2)).sum())), "data/perturb_report.pkl")
print("excel ok")

# ================================================================= グラフ
SHORT = {"NDX 1985-2026": "NDX 1985-2026【IS】", "S&P500 1950-1985": "S&P500 1950-1985", "NASDAQ総合 1974-1985": "NASDAQ総合 1974-1985",
         "NDX 2022/9-2026": "NDX 2022/9-2026", "S&P500 1985-2026": "S&P500 1985-2026", "ダウ 1995-2026": "ダウ 1995-2026",
         "ラッセル2000 1991-2026": "ラッセル2000 1991-2026"}
oku = mt.FuncFormatter(lambda x, _: f"{x:,.0f}億")

# fig8: NDX 締め日21通り + 暦日締め + 約定遅延
g = P1[P1.set == SETORDER[0]].set_index("var").final / 1e8
lagv = P2[P2.set == SETORDER[0]].set_index("var").final / 1e8
d3, d1 = REF.loc[SETORDER[0], "3倍単純積立"] / 1e8, REF.loc[SETORDER[0], "1倍単純積立"] / 1e8
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 5.6), dpi=110, gridspec_kw=dict(width_ratios=[3.3, 1]), sharey=True)
xs = list(range(len(KV))) + [len(KV) + 1 + i for i in range(len(DV))]
vals = [g[v] for v in KV + DV]
cols = [ORANGE if v == "k+0" else (BLUE if v.startswith("k") else AQUA) for v in KV + DV]
a1.bar(xs, vals, color=cols, width=0.72, edgecolor="white", lw=1)
med = np.median([g[v] for v in KV])
for y, t, ls in [(med, f"21通りの中央値 {med:.0f}億", "--"), (d3, f"3倍単純積立 {d3:.1f}億", ":"), (d1, f"1倍単純積立 {d1:.1f}億", ":")]:
    a1.axhline(y, color=INK2, lw=1, ls=ls); a1.text(len(xs) + 5.3, y, t, va="center", fontsize=8.5, color=INK2)
a1.text(KV.index("k+0"), g["k+0"] + 3, f"基準\n{g['k+0']:.0f}億", ha="center", fontsize=8.5, color=INK, fontweight="bold")
for v in ["k-7", "k-2", "k+3"]:
    a1.text(KV.index(v), max(g[v], d3) + 2.5, f"{g[v]:.0f}", ha="center", fontsize=8.5, color=INK2)
a1.set_xticks(xs); a1.set_xticklabels([v[1:] if v.startswith("k") else v[1:] + "日" for v in KV + DV], fontsize=8.5)
a1.text(10, -22, "月足の締め日（月末最終営業日から何営業日ずらすか）", ha="center", fontsize=9, color=INK2)
a1.text(len(KV) + 3, -22, "暦日締め", ha="center", fontsize=9, color=INK2)
a1.yaxis.set_major_formatter(oku); a1.set_ylim(0, 150); a1.set_xlim(-0.8, len(xs) + 5)
a1.grid(axis="y", alpha=0.25)
a1.set_title("締め日を変えると最終資産は12億〜134億円（11倍の幅）。基準の38億円は21通り中16位で、当たり位相ではない",
             loc="left", fontsize=11, fontweight="bold")
a2.bar(range(len(LAGS)), [lagv[f"lag{l}"] for l in LAGS], color=[GRAY if l == 0 else (ORANGE if l == 1 else BLUE) for l in LAGS],
       width=0.7, edgecolor="white", lw=1)
for i, l in enumerate(LAGS):
    a2.text(i, lagv[f"lag{l}"] + 2, f"{lagv[f'lag{l}']:.0f}", ha="center", fontsize=8.5, color=INK2)
a2.set_xticks(range(len(LAGS))); a2.set_xticklabels([f"{l}日後" for l in LAGS], fontsize=8.5)
a2.text(2.5, -22, "約定日（締め日の何営業日後か）", ha="center", fontsize=9, color=INK2)
a2.set_title("約定を遅らせると単調に悪化", loc="left", fontsize=11, fontweight="bold"); a2.grid(axis="y", alpha=0.25)
fig.text(0.01, 0.01, "NDX 1985/10〜2026/10、現実コストC・名目3万円/月・税引後。橙=基準（月末締め・翌営業日引け）、青=締め日シフト、緑=暦日締め、灰=0日後（当日引け、実行不能）",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.06, 1, 1)); fig.savefig(OUT / "fig8_締め日シフト.png"); plt.close()

# fig9: 全セット — 締め日21通りの最終資産 ÷ 1倍単純積立
fig, ax = plt.subplots(figsize=(12, 5.8), dpi=110)
for yi, s in enumerate(SETORDER):
    y = len(SETORDER) - 1 - yi
    gs = P1[(P1.set == s) & P1["var"].isin(KV)].set_index("var").final
    r1 = gs / REF.loc[s, "1倍単純積立"]
    jit = (np.random.default_rng(2).random(len(r1)) - 0.5) * 0.22
    ax.scatter(r1.values, y + jit, s=26, color=BLUE, alpha=0.6, edgecolor="white", lw=0.5, zorder=3, label="締め日21通り" if yi == 0 else None)
    ax.scatter([r1["k+0"]], [y], marker="D", s=70, color=ORANGE, edgecolor=INK, lw=1.1, zorder=4, label="基準（月末締め）" if yi == 0 else None)
    x3 = REF.loc[s, "3倍単純積立"] / REF.loc[s, "1倍単純積立"]
    ax.plot([x3, x3], [y - 0.32, y + 0.32], color=INK, lw=2.2, zorder=2, label="3倍単純積立" if yi == 0 else None)
    w = SUM.loc[s]
    ax.text(45, y, f"3倍積立に勝つ {int(w.w3)}/21　1倍積立に勝つ {int(w.w1)}/21", va="center", fontsize=8.5, color=INK2)
ax.axvline(1, color=INK2, lw=1, ls="--"); ax.text(1.02, len(SETORDER) - 0.45, "1倍単純積立と同じ", fontsize=8.5, color=INK2)
ax.set_xscale("log"); ax.set_xlim(0.08, 260)
ax.set_xticks([0.1, 0.3, 1, 3, 10]); ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda x, _: f"{x:g}倍"))
ax.set_yticks(range(len(SETORDER))[::-1]); ax.set_yticklabels([SHORT[s] for s in SETORDER], fontsize=9)
ax.axhspan(len(SETORDER) - 1.5, len(SETORDER) - 0.5, color="#f0efec", zorder=0)
ax.grid(axis="x", alpha=0.25); ax.set_xlabel("税引後最終資産 ÷ 1倍単純積立（対数目盛）")
ax.legend(loc="lower center", bbox_to_anchor=(0.4, 1.0), ncol=3, frameon=False, fontsize=9)
ax.set_title("NDX以外では、どの締め日でも3倍単純積立に勝てない（126通り中0）", loc="left", fontsize=12, fontweight="bold", pad=24)
fig.text(0.01, 0.01, "現実コストC・名目3万円/月・全期間。3倍単純積立はNDXで2002年・2009年にほぼ0になる（実在ETFなら繰上償還の可能性）。縦の黒線=3倍単純積立",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT / "fig9_締め日シフト全セット.png"); plt.close()

# fig10: エピソード除去
e = EP.copy().reset_index(drop=True)
fig, ax = plt.subplots(figsize=(11.5, 7.2), dpi=110)
ys = np.arange(len(e))[::-1]
colr = [ORANGE if k.startswith("退避") else BLUE for k in e.kind]
ax.barh(ys, e.dlog * 100, color=colr, height=0.68, edgecolor="white", lw=1)
lab_ = []
for i, x in e.iterrows():
    a = f"{x.d1:%Y/%m}" + (f"→{x.d2:%Y/%m}" if pd.notna(x.d2) else "→保有中")
    lab_.append(("退避 " if x.kind.startswith("退避") else "保有 ") + a)
    v = np.expm1(x.dlog) * 100
    ax.text(x.dlog * 100 + (4 if x.dlog >= 0 else -4), ys[i], f"{v:+.0f}%", va="center", ha="left" if x.dlog >= 0 else "right",
            fontsize=8, color=INK2)
ax.set_yticks(ys); ax.set_yticklabels(lab_, fontsize=8.5)
ax.axvline(0, color=INK, lw=1); ax.axvline(-np.log(2) * 100, color=INK2, lw=0.8, ls=":")
ax.text(-np.log(2) * 100, len(e) - 0.2, "半分", ha="center", fontsize=8, color=INK2)
tkr = [0.03, 0.1, 0.25, 0.5, 1, 2]
ax.set_xticks([np.log(t) * 100 for t in tkr]); ax.set_xticklabels(["−97%", "−90%", "−75%", "−50%", "±0", "+100%"])
ax.set_xlim(-400, 130)
ax.grid(axis="x", alpha=0.25)
ax.set_xlabel("その1回を消したときの税引後最終資産の変化（対数目盛、基準38.0億円比）")
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=ORANGE, label="退避を消す（売らずに3倍を持ち続けた場合）"),
                   Patch(color=BLUE, label="保有を消す（買わずに1倍で待ち続けた場合）")], loc="lower left", frameon=False, fontsize=9)
e00 = e[e.d1 == pd.Timestamp("2000-09-29")].iloc[0]
ax.set_title(f"2000/9の退避1回を消すと{P['base'] / 1e8:.0f}億→{e00.final / 1e8:.1f}億円（{np.expm1(e00.dlog):+.0%}）。退避12回のうち役立ったのは3回だけ",
             loc="left", fontsize=12, fontweight="bold")
fig.text(0.01, 0.01, "NDX 1985/10〜2026/10、現実コストC・名目3万円/月。左に長い=その1回が資産を支えた、右=その1回は損だった（ダマシ）", fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT / "fig10_エピソード除去.png"); plt.close()
print("charts ok")
