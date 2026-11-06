"""OOS検証のExcel(数式で突合)とグラフ。前提: python3 oos.py 実行済み"""
import sys
sys.path.insert(0, ".")
from oos import *
import xlsxwriter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.ticker as mt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

OUT = Path("./out"); OUT.mkdir(exist_ok=True)
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams.update({"font.family": "IPAGothic", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, AQUA, GRAY, INK, INK2 = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984", "#0b0b0b", "#52514e"

O = pd.read_pickle("data/oos.pkl"); R = O["res"]; COST = O["cost"]
SETORDER = [s[0] for s in SETS]
KIND = {s[0]: s[1] for s in SETS}

# ---------------------------------------------------------------- ① IS で閾値を選ぶ（事前ルール: IS全期間の税引後最終資産が最大）
RATEV = list(variants_rate(Cfg(name="x")).keys())
isg = R[(R.set == SETORDER[0]) & (R.win == "全期間") & (R["var"].isin(RATEV))].set_index("var").loc[RATEV]
SEL = isg.final.idxmax()
print("IS選択:", SEL)

full = R[R.win == "全期間"].pivot(index="var", columns="set", values="final")[SETORDER]
contrib = R[R.win == "全期間"].groupby("set").contrib.first()[SETORDER]
mdd = R[R.win == "全期間"].pivot(index="var", columns="set", values="mdd")[SETORDER]
win = R[R.win == "10年窓"].copy()
base = win[win["var"] == "3倍固定"].set_index(["set", "start"]).final
win["base"] = [base[(a, b)] for a, b in zip(win.set, win.start)]
win["lr"] = np.log(win.final / win.base)
win = win[(win.test != "参考") & (win["var"] != "3倍固定")]


def wstats(g):
    lr = g.lr.values
    return pd.Series(dict(n=len(lr), w=int((lr > 1e-9).sum()), l=int((lr < -1e-9).sum()),
                          t=int((np.abs(lr) <= 1e-9).sum()), med=float(np.median(lr)) if len(lr) else np.nan))


WS = win.groupby(["set", "var"]).apply(wstats).reset_index()

# ---------------------------------------------------------------- Excel
wb = xlsxwriter.Workbook(str(OUT / "MPI_ver4_OOS検証.xlsx"))
F = dict(h=wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True, "valign": "top", "border": 1}),
         yen=wb.add_format({"num_format": "#,##0"}), x1=wb.add_format({"num_format": "0.0"}), pct=wb.add_format({"num_format": "0.0%"}),
         pct2=wb.add_format({"num_format": "0.00%"}), f6=wb.add_format({"num_format": "0.000000"}), sci=wb.add_format({"num_format": "0.00E+00"}),
         title=wb.add_format({"bold": True, "font_size": 14}), b=wb.add_format({"bold": True}),
         wrap=wb.add_format({"text_wrap": True, "valign": "top"}), d=wb.add_format({"num_format": "yyyy-mm-dd"}),
         sel=wb.add_format({"bold": True, "bg_color": "#FFF2CC"}))


def hdr(ws, r, cols):
    for j, x in enumerate(cols):
        ws.write(r, j, x, F["h"])


# --- 概要（全期間・倍率と基準比を数式で）
ws = wb.add_worksheet("概要")
ws.set_column(0, 0, 30); ws.set_column(1, 20, 13)
ws.write(0, 0, "改良案のアウトオブサンプル検証（①高金利期は2倍 ②月末引け約定）", F["title"])
ws.write(1, 0, f"現実コストC（SBI手数料・為替・日本税制・較正済みファンドコスト）、名目3万円/月、税引後。ISで選んだ①の規則: {SEL}")
ws.write(3, 0, "最終資産 ÷ 投入元本（倍）", F["b"])
hdr(ws, 4, ["案 \\ 検証セット"] + SETORDER)
ws.write(5, 0, "区分"); [ws.write(5, j + 1, KIND[s]) for j, s in enumerate(SETORDER)]
ws.write(6, 0, "投入元本(円)"); [ws.write_number(6, j + 1, contrib[s], F["yen"]) for j, s in enumerate(SETORDER)]
SHOW = ["3倍固定", SEL, "2倍固定", "月末引け(C-MOC)", "現実的MOC(前日判定)", "1倍単純積立", "3倍単純積立"]
r0 = 8
ws.write(r0 - 1, 0, "税引後最終資産(円)", F["b"])
for i, v in enumerate(SHOW):
    ws.write(r0 + i, 0, v, F["sel"] if v == SEL else None)
    for j, s in enumerate(SETORDER):
        ws.write_number(r0 + i, j + 1, full.loc[v, s], F["yen"])
r1 = r0 + len(SHOW) + 1
ws.write(r1, 0, "倍率（数式 = 最終資産/元本）", F["b"])
for i, v in enumerate(SHOW):
    ws.write(r1 + 1 + i, 0, v)
    for j in range(len(SETORDER)):
        c = xlsxwriter.utility.xl_col_to_name(j + 1)
        ws.write_formula(r1 + 1 + i, j + 1, f"={c}{r0 + i + 1}/{c}$7", F["x1"])
r2 = r1 + len(SHOW) + 2
ws.write(r2, 0, "3倍固定(翌営業日引け)比（数式）", F["b"])
for i, v in enumerate(SHOW[1:5]):
    ws.write(r2 + 1 + i, 0, v)
    for j in range(len(SETORDER)):
        c = xlsxwriter.utility.xl_col_to_name(j + 1)
        ws.write_formula(r2 + 1 + i, j + 1, f"={c}{r0 + 2 + i}/{c}${r0 + 1}-1", F["pct"])
r3 = r2 + 7
ws.write(r3, 0, "最大ドローダウン（時間加重）", F["b"])
for i, v in enumerate(SHOW):
    ws.write(r3 + 1 + i, 0, v)
    for j, s in enumerate(SETORDER):
        ws.write_number(r3 + 1 + i, j + 1, mdd.loc[v, s], F["pct"])
ws.freeze_panes(5, 1)

# --- 設計
ws = wb.add_worksheet("検証設計")
ws.set_column(0, 0, 26); ws.set_column(1, 1, 110)
rows_ = [("項目", "内容"),
         ("IS(作成に使った期間)", "NDX 1985/10〜2026/10。記事ルール(〜2022/8)も改良案2つ(前回検証)も、この期間の結果を見て作られた"),
         ("OOS-時間", "S&P500 1950/1〜1985/9、NASDAQ総合 1974/1〜1985/9。NDX誕生前で誰も見ていない。1970〜80年代の高金利(最大15%)を含み①の本番"),
         ("OOS-事後", "NDX 2022/9〜2026/10。記事ルールにとっては公開後。ただし改良案はこの期間も見て作ったので弱いOOS"),
         ("OOS-資産", "S&P500 1985/10〜、ダウ 1995/1〜、ラッセル2000 1991/1〜（〜2026/10）。同時期・別指数。NDXと相関が高いので中程度のOOS"),
         ("①の規則の選び方", f"閾値2〜6%×(entry=買シグナル時のみ判定 / monthly=積立日ごとに再判定して乗換)の10通り+2倍固定から、IS全期間の税引後最終資産が最大のものを機械的に選択 → {SEL}。OOSでは一切変更しない"),
         ("①の金利", "前営業日の米3M T-bill(DTB3、1954年以前はTB3MS月次)。2倍の総合コストは各指数の実在2倍ETF(QLD/SSO/DDM/UWM)で較正"),
         ("②の3方式", "翌営業日引け(C, 基準) / 月末引け(C-MOC: 月末終値で判定し同じ終値で約定＝厳密には実行不能) / 現実的MOC(月末前日の終値までで判定→月末引けで約定＝実行可能な下限)"),
         ("②の分解", "C-MOCは『約定を月末に』『積立を月末に(=月初より約1か月遅い入金)』の2変更を含むので、片方ずつも計算"),
         ("評価", "全期間 + 10年ローリング窓(毎年1月開始)。窓は重なるので独立な試行ではない（勝率は記述統計で、有意性検定ではない）"),
         ("配当(仮定)", "S&P500: 1993/1以前はShiller月次配当利回り、以降SPY。ダウ: 1998以前Shiller、以降DIA。ラッセル: 2000/5以前Shiller×0.6、以降IWM。NASDAQ総合: Shiller×0.5（全期間仮定）"),
         ("その他", "1971年以前の為替は360円固定。1962年以前のS&P500、1984年以前のNASDAQ総合は高値/安値がなく終値で代用（月足の高安は日次終値の最大/最小）"),
         ]
for i, rr in enumerate(rows_):
    for j, x in enumerate(rr):
        ws.write(i, j, x, F["h"] if i == 0 else F["wrap"])

# --- ① IS選択（数式で最大を選び、Pythonの選択と一致するか）
ws = wb.add_worksheet("①IS選択")
ws.set_column(0, 0, 24); ws.set_column(1, 5, 16)
hdr(ws, 0, ["案(IS: NDX 1985-2026)", "税引後最終資産(円)", "倍率(数式)", "3倍固定比(数式)", "最大DD", "乗換回数"])
for i, v in enumerate(RATEV):
    x = isg.loc[v]
    ws.write(i + 1, 0, v); ws.write_number(i + 1, 1, x.final, F["yen"])
    ws.write_formula(i + 1, 2, f"=B{i + 2}/{x.contrib}", F["x1"]); ws.write_formula(i + 1, 3, f"=B{i + 2}/$B$2-1", F["pct"])
    ws.write_number(i + 1, 4, x.mdd, F["pct"]); ws.write_number(i + 1, 5, x.switches)
n = len(RATEV) + 1
ws.write(n + 1, 0, "Excelが選んだ案(数式)", F["b"]); ws.write_formula(n + 1, 1, f"=INDEX(A2:A{n},MATCH(MAX(B2:B{n}),B2:B{n},0))")
ws.write(n + 2, 0, "Pythonが選んだ案"); ws.write(n + 2, 1, SEL)
ws.write(n + 3, 0, "一致(数式)", F["b"]); ws.write_formula(n + 3, 1, f"=EXACT(B{n + 2},B{n + 3})")

# --- 窓データ & 集計（COUNTIFS/MEDIAN(IF) で再集計し、Pythonと突合）
ws = wb.add_worksheet("窓データ")
cols = ["検証", "セット", "案", "開始", "終了", "最終資産", "基準(3倍固定・翌日)最終資産", "対数比(数式)", "判定(数式)"]
hdr(ws, 0, cols); ws.set_column(0, 2, 20); ws.set_column(3, 8, 14)
for i, x in enumerate(win.itertuples(), start=1):
    ws.write(i, 0, x.test); ws.write(i, 1, x.set); ws.write(i, 2, x.var); ws.write(i, 3, x.start); ws.write(i, 4, x.end)
    ws.write_number(i, 5, x.final, F["yen"]); ws.write_number(i, 6, x.base, F["yen"])
    ws.write_formula(i, 7, f"=LN(F{i + 1}/G{i + 1})", F["f6"])
    ws.write_formula(i, 8, f'=IF(ABS(H{i + 1})<=1E-9,"引分",IF(H{i + 1}>0,"勝","負"))')
NW = len(win) + 1
ws.autofilter(0, 0, NW - 1, 8); ws.freeze_panes(1, 0)
ws = wb.add_worksheet("窓集計")
ws.set_column(0, 1, 22); ws.set_column(2, 14, 11)
hdr(ws, 0, ["セット", "案", "窓数", "勝", "負", "引分", "中央値(基準比,数式)", "Py窓数", "Py勝", "Py負", "Py引分", "Py中央値", "差(勝)", "差(中央値)"])
k = 1
for x in WS.itertuples():
    rr = k + 1
    ws.write(k, 0, x.set); ws.write(k, 1, x.var)
    cond = f'窓データ!$B$2:$B${NW},$A{rr},窓データ!$C$2:$C${NW},$B{rr}'
    ws.write_formula(k, 2, f"=COUNTIFS({cond})")
    ws.write_formula(k, 3, f'=COUNTIFS({cond},窓データ!$I$2:$I${NW},"勝")')
    ws.write_formula(k, 4, f'=COUNTIFS({cond},窓データ!$I$2:$I${NW},"負")')
    ws.write_formula(k, 5, f'=COUNTIFS({cond},窓データ!$I$2:$I${NW},"引分")')
    ws.write_array_formula(k, 6, k, 6, f'{{=EXP(MEDIAN(IF((窓データ!$B$2:$B${NW}=$A{rr})*(窓データ!$C$2:$C${NW}=$B{rr}),窓データ!$H$2:$H${NW})))-1}}', F["pct"])
    ws.write_number(k, 7, x.n); ws.write_number(k, 8, x.w); ws.write_number(k, 9, x.l); ws.write_number(k, 10, x.t)
    ws.write_number(k, 11, np.expm1(x.med), F["pct"])
    ws.write_formula(k, 12, f"=D{rr}-I{rr}"); ws.write_formula(k, 13, f"=G{rr}-L{rr}", F["sci"])
    k += 1
ws.write(k + 1, 0, "最大|差|(勝)", F["b"]); ws.write_array_formula(k + 1, 2, k + 1, 2, f"{{=MAX(ABS(M2:M{k}))}}")
ws.write(k + 2, 0, "最大|差|(中央値)", F["b"]); ws.write_array_formula(k + 2, 2, k + 2, 2, f"{{=MAX(ABS(N2:N{k}))}}", F["sci"])
ws.freeze_panes(1, 2); ws.autofilter(0, 0, k - 1, 13)
WS_ROWS = k

# --- 数式検算: S&P500 1950-1985 を日次の生データから数式だけで再計算（①6%monthly・月末引け・税/手数料/為替なし）
d = pd.read_pickle("data/daily_GSPC.pkl")
c3, c2 = COST["GSPC"]
thr = 0.06
cfgL = Cfg(name="ledger", lev_cost=c3, lev_cost_lo=c2, financing=True, one_er=0.0015, dividends=True, exec_lag=0,
           contrib_at_month_end=True, tax_on=False, infl_adj=False, rate_thr=thr, rate_mode="monthly",
           start="1950-01", end="1985-09")
sigG = O["sig"]["GSPC"]
rL, hL, tL = run(d, sigG, cfgL)
pyv = hL.value_ccy.groupby(hL.index.to_period("M")).last()
dd = d.loc["1950-01":"1985-09"]
ws = wb.add_worksheet("検算_日次")
hdr(ws, 0, ["日付", "S&P500終値", "暦日数", "米3M金利", "1倍配当(日)", "r(数式)", "3倍日次(数式)", "2倍日次(数式)", "1倍日次(数式)",
            "3倍指数(数式)", "2倍指数(数式)", "1倍価格(数式)", "配当再投資係数(数式)", "月末", "前営業日金利(数式)"])
ws.set_column(0, 0, 11); ws.set_column(1, 14, 12)
ws.write(1, 16, "c3(3倍コスト)"); ws.write_number(1, 17, c3, F["pct2"])
ws.write(2, 16, "c2(2倍コスト)"); ws.write_number(2, 17, c2, F["pct2"])
ws.write(3, 16, "1倍経費率"); ws.write_number(3, 17, 0.0015, F["pct2"])
prev_c = d.c.loc[:"1949-12"].iloc[-1]
per = dd.index.to_period("M"); islast = np.r_[per[1:] != per[:-1], True]
for i, (dt_, x) in enumerate(dd.iterrows(), start=1):
    R_ = i + 1
    ws.write_datetime(i, 0, dt_.to_pydatetime(), F["d"]); ws.write_number(i, 1, x.c); ws.write_number(i, 2, x["dt"])
    ws.write_number(i, 3, x["rf"]); ws.write_number(i, 4, x["dy"])
    if i == 1:
        ws.write_formula(i, 5, f"=B2/{prev_c}-1")
        for j in (9, 10, 11, 12):
            ws.write_number(i, j, 1.0)
        ws.write_formula(i, 14, "=D2")
    else:
        ws.write_formula(i, 5, f"=B{R_}/B{R_ - 1}-1")
        ws.write_formula(i, 9, f"=J{R_ - 1}*(1+G{R_})"); ws.write_formula(i, 10, f"=K{R_ - 1}*(1+H{R_})")
        ws.write_formula(i, 11, f"=L{R_ - 1}*(1+I{R_})"); ws.write_formula(i, 12, f"=M{R_ - 1}*(1+E{R_})")
        ws.write_formula(i, 14, f"=D{R_ - 1}")
    ws.write_formula(i, 6, f"=3*(F{R_}+E{R_})-2*D{R_}*C{R_}/365-$R$2*C{R_}/365")
    ws.write_formula(i, 7, f"=2*(F{R_}+E{R_})-1*D{R_}*C{R_}/365-$R$3*C{R_}/365")
    ws.write_formula(i, 8, f"=F{R_}-$R$4*C{R_}/365")
    ws.write(i, 13, 1 if islast[i - 1] else 0)
ND = len(dd) + 1
ws.freeze_panes(1, 1)

ws = wb.add_worksheet("検算_月次台帳")
H_ = ["月", "月末日", "シグナル(Py)", "前営業日金利(数式)", "3倍月次係数", "2倍月次係数", "1倍月次係数(配当込)",
      "期初 状態", "レバ評価額(期初)", "倍率(期初)", "1倍評価額(期初)", "現金(期初)", "振替額(期初)",
      "レバ 成長後", "1倍 成長後", "売実行", "買実行", "状態", "倍率", "レバ 約定後", "1倍 約定後", "現金 約定後", "振替額",
      "積立", "レバ 期末", "1倍 期末", "現金 期末", "総資産(数式)", "総資産(Python)", "乖離率(数式)"]
hdr(ws, 0, H_); ws.set_column(0, 1, 11); ws.set_column(2, 29, 12)
ws.write(0, 31, "閾値"); ws.write_number(0, 32, thr, F["pct"]); ws.write(1, 31, "積立"); ws.write_number(1, 32, 30000)
ws.write(2, 31, "振替率"); ws.write_number(2, 32, 0.01, F["pct"])
months = list(pyv.index)
sg = sigG.sig.reindex(pd.PeriodIndex(months, freq="M")).fillna(0).astype(int).values
DREF = f"検算_日次!$A$2:$A${ND}"
for i, pm in enumerate(months, start=1):
    R_ = i + 1
    T = dd.index[per == pm][-1]
    ws.write(i, 0, str(pm)); ws.write_datetime(i, 1, T.to_pydatetime(), F["d"]); ws.write_number(i, 2, int(sg[i - 1]))
    mt_ = f"MATCH(B{R_},{DREF},0)"
    ws.write_formula(i, 3, f"=INDEX(検算_日次!$O$2:$O${ND},{mt_})")
    if i == 1:
        for j, col in ((4, "J"), (5, "K")):
            ws.write_formula(i, j, f"=INDEX(検算_日次!${col}$2:${col}${ND},{mt_})")
        ws.write_formula(i, 6, f"=INDEX(検算_日次!$L$2:$L${ND},{mt_})*INDEX(検算_日次!$M$2:$M${ND},{mt_})")
        ws.write(i, 7, "out"); ws.write_number(i, 8, 0); ws.write_number(i, 9, 3); ws.write_number(i, 10, 0)
        ws.write_number(i, 11, 0); ws.write_number(i, 12, 0)
    else:
        pmt = f"MATCH(B{R_ - 1},{DREF},0)"
        for j, col in ((4, "J"), (5, "K")):
            ws.write_formula(i, j, f"=INDEX(検算_日次!${col}$2:${col}${ND},{mt_})/INDEX(検算_日次!${col}$2:${col}${ND},{pmt})")
        ws.write_formula(i, 6, f"=INDEX(検算_日次!$L$2:$L${ND},{mt_})*INDEX(検算_日次!$M$2:$M${ND},{mt_})"
                               f"/(INDEX(検算_日次!$L$2:$L${ND},{pmt})*INDEX(検算_日次!$M$2:$M${ND},{pmt}))")
        ws.write_formula(i, 7, f"=R{R_ - 1}"); ws.write_formula(i, 8, f"=Y{R_ - 1}"); ws.write_formula(i, 9, f"=S{R_ - 1}")
        ws.write_formula(i, 10, f"=Z{R_ - 1}"); ws.write_formula(i, 11, f"=AA{R_ - 1}"); ws.write_formula(i, 12, f"=W{R_ - 1}")
    ws.write_formula(i, 13, f"=I{R_}*IF(J{R_}=3,E{R_},F{R_})")
    ws.write_formula(i, 14, f"=K{R_}*G{R_}")
    ws.write_formula(i, 15, f'=AND(C{R_}=-1,H{R_}="long")')
    ws.write_formula(i, 16, f'=AND(C{R_}=1,H{R_}="out")')
    ws.write_formula(i, 17, f'=IF(P{R_},"out",IF(Q{R_},"long",H{R_}))')
    ws.write_formula(i, 18, f'=IF(R{R_}="long",IF(D{R_}>$AG$1,2,3),J{R_})')
    ws.write_formula(i, 19, f"=IF(P{R_},0,IF(Q{R_},L{R_}+O{R_},N{R_}))")
    ws.write_formula(i, 20, f"=IF(Q{R_},0,O{R_})")
    ws.write_formula(i, 21, f"=IF(P{R_},L{R_}+N{R_},IF(Q{R_},0,L{R_}))")
    ws.write_formula(i, 22, f"=IF(P{R_},V{R_}*$AG$3,M{R_})")
    ws.write_formula(i, 23, "=$AG$2")
    ws.write_formula(i, 24, f'=T{R_}+IF(R{R_}="long",X{R_},0)')
    ws.write_formula(i, 25, f'=U{R_}+IF(R{R_}="out",X{R_}+MIN(W{R_},V{R_}),0)')
    ws.write_formula(i, 26, f'=V{R_}-IF(R{R_}="out",MIN(W{R_},V{R_}),0)')
    ws.write_formula(i, 27, f"=Y{R_}+Z{R_}+AA{R_}", F["yen"])
    ws.write_number(i, 28, pyv.loc[pm], F["yen"])
    ws.write_formula(i, 29, f"=AB{R_}/AC{R_}-1", F["sci"])
NM = len(months) + 1
ws.write(NM + 1, 0, "最大|乖離率|", F["b"]); ws.write_array_formula(NM + 1, 2, NM + 1, 2, f"{{=MAX(ABS(AD2:AD{NM}))}}", F["sci"])
ws.write(NM + 2, 0, "2倍だった月数(数式)"); ws.write_formula(NM + 2, 2, f'=COUNTIFS(R2:R{NM},"long",S2:S{NM},2)')
ws.freeze_panes(1, 2)
LEDGER_N = NM

# --- 数式検算: MACD(12,26,9) を月次終値から（Pine EMA: 先頭n本の単純平均で初期化）
mG = monthly_bars(d).loc[:"2026-10"]
ws = wb.add_worksheet("検算_MACD")
hdr(ws, 0, ["月", "終値", "EMA12(数式)", "EMA26(数式)", "MACD(数式)", "シグナル9(数式)", "MACD(Py)", "シグナル(Py)", "差MACD", "差シグナル"])
ws.set_column(0, 9, 13)
C_ = mG.c.values
for i in range(len(mG)):
    R_ = i + 2
    ws.write(i + 1, 0, str(mG.index[i])); ws.write_number(i + 1, 1, C_[i])
    if i == 11: ws.write_formula(i + 1, 2, "=AVERAGE(B2:B13)")
    elif i > 11: ws.write_formula(i + 1, 2, f"=2/13*B{R_}+(1-2/13)*C{R_ - 1}")
    if i == 25: ws.write_formula(i + 1, 3, "=AVERAGE(B2:B27)")
    elif i > 25: ws.write_formula(i + 1, 3, f"=2/27*B{R_}+(1-2/27)*D{R_ - 1}")
    if i >= 25: ws.write_formula(i + 1, 4, f"=C{R_}-D{R_}")
    if i == 33: ws.write_formula(i + 1, 5, "=AVERAGE(E27:E35)")
    elif i > 33: ws.write_formula(i + 1, 5, f"=2/10*E{R_}+(1-2/10)*F{R_ - 1}")
    if i >= 25:
        ws.write_number(i + 1, 6, sigG.macd.iloc[i]); ws.write_formula(i + 1, 8, f"=E{R_}/G{R_}-1", F["sci"])
    if i >= 33:
        ws.write_number(i + 1, 7, sigG.signal.iloc[i]); ws.write_formula(i + 1, 9, f"=F{R_}/H{R_}-1", F["sci"])
NMC = len(mG) + 1
ws.write(0, 11, "最大|差|MACD"); ws.write_array_formula(0, 12, 0, 12, f"{{=MAX(ABS(I28:I{NMC}))}}", F["sci"])
ws.write(1, 11, "最大|差|シグナル"); ws.write_array_formula(1, 12, 1, 12, f"{{=MAX(ABS(J36:J{NMC}))}}", F["sci"])
ws.freeze_panes(1, 1)

# --- シグナル比較（当日判定 vs 前日判定）
ws = wb.add_worksheet("②シグナル比較")
hdr(ws, 0, ["指数", "月末日", "当日終値で判定", "前日終値で判定", "一致"]); ws.set_column(0, 4, 14)
k = 1
for ix in ["NDX", "GSPC", "IXIC", "DJI", "RUT"]:
    s_ = O["sig"][ix]; fu = {r.last_day: int(r.sig) for _, r in s_[s_.sig != 0].iterrows()}; t1 = O["tm1"][ix]
    for day in sorted(set(fu) | set(t1)):
        ws.write(k, 0, ix); ws.write_datetime(k, 1, day.to_pydatetime(), F["d"])
        ws.write(k, 2, fu.get(day, "")); ws.write(k, 3, t1.get(day, ""))
        ws.write_formula(k, 4, f'=IF(C{k + 1}=D{k + 1},"○","×")'); k += 1
ws.autofilter(0, 0, k - 1, 4)
ws = wb.add_worksheet("②2000年9月")
hdr(ws, 0, ["日付", "NDX高値", "NDX安値", "NDX終値"]); ws.set_column(0, 3, 13)
nd = pd.read_pickle("data/daily_NDX.pkl").loc["2000-09-20":"2000-09-29"]
for i, (dt_, x) in enumerate(nd.iterrows(), start=1):
    ws.write_datetime(i, 0, dt_.to_pydatetime(), F["d"]); ws.write_number(i, 1, x.h); ws.write_number(i, 2, x.l); ws.write_number(i, 3, x.c)
ws.write(len(nd) + 2, 0, "最終日の騰落(数式)"); ws.write_formula(len(nd) + 2, 1, f"=D{len(nd) + 1}/D{len(nd)}-1", F["pct"])
ws.write(len(nd) + 3, 0, "当日判定=売り(2000/9/29)、前日判定=売りなし → 3倍を2002/5まで保有し資産がほぼ0に")
wb.close()

# 突合用に保存
pd.to_pickle(dict(SEL=SEL, WS=WS, WS_ROWS=WS_ROWS, LEDGER_N=LEDGER_N, ledger_switch=rL["n_switch"]), "data/oos_report.pkl")

# ================================================================= グラフ
SHORT = {"NDX 1985-2026": "NDX\n1985-2026\n【IS】", "S&P500 1950-1985": "S&P500\n1950-1985", "NASDAQ総合 1974-1985": "NASDAQ総合\n1974-1985",
         "NDX 2022/9-2026": "NDX\n2022/9-2026", "S&P500 1985-2026": "S&P500\n1985-2026", "ダウ 1995-2026": "ダウ\n1995-2026",
         "ラッセル2000 1991-2026": "ラッセル2000\n1991-2026"}
# fig5 ①ヒートマップ
rows5 = ["2倍固定"] + [v for v in RATEV if "超" in v]
M5 = (full.loc[rows5] / full.loc["3倍固定"] - 1) * 100
cmap = LinearSegmentedColormap.from_list("div", ["#d03b3b", "#f0efec", BLUE])
fig, ax = plt.subplots(figsize=(11.5, 6.6), dpi=110)
im = ax.imshow(np.clip(M5.values, -60, 60), cmap=cmap, vmin=-60, vmax=60, aspect="auto")
for i in range(M5.shape[0]):
    for j in range(M5.shape[1]):
        v = M5.values[i, j]
        ax.text(j, i, "±0" if abs(v) < 0.05 else f"{v:+.0f}%", ha="center", va="center", fontsize=9,
                color="white" if abs(v) > 40 else INK, fontweight="bold" if rows5[i] == SEL else None)
ax.set_xticks(range(len(SETORDER))); ax.set_xticklabels([SHORT[s] for s in SETORDER], fontsize=9)
ax.set_yticks(range(len(rows5))); ax.set_yticklabels([("▶ " + r + "（ISで選択）") if r == SEL else r for r in rows5], fontsize=9)
for t in ax.get_yticklabels():
    if t.get_text().startswith("▶"): t.set_fontweight("bold")
ax.axvline(0.5, color=INK, lw=1.5); ax.axvline(2.5, color=INK2, lw=0.8, ls=":"); ax.axvline(3.5, color=INK2, lw=0.8, ls=":")
ax.text(0, -0.9, "作成に使った期間", ha="center", fontsize=8.5, color=INK2)
ax.text(1.5, -0.9, "使っていない期間（1985年以前）", ha="center", fontsize=8.5, color=INK2)
ax.text(5, -0.9, "別の指数（同じ時期）", ha="center", fontsize=8.5, color=INK2)
ax.tick_params(length=0); [s.set_visible(False) for s in ax.spines.values()]
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01); cb.set_label("「常に3倍」比の税引後最終資産（%、±60%で頭打ち）", fontsize=8.5)
ax.set_title("① 金利が高い時は2倍：ISで選んだ6%規則はOOSで損はしないが、閾値を少し変えると符号が反転",
             loc="left", fontsize=12, fontweight="bold", pad=26)
fig.text(0.01, 0.01, "現実コストC・名目3万円/月・全期間。entry=買う時だけ判定 / monthly=毎月判定し乗換（乗換時に課税）。青=改善、赤=悪化", fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT / "fig5_金利ルールOOS.png"); plt.close()

# fig6 ② 10年窓の分布
fig, ax = plt.subplots(figsize=(11.5, 6.2), dpi=110)
sets6 = [s for s in SETORDER if s != "NDX 2022/9-2026"]
ylab = []
for yi, s in enumerate(sets6):
    for k, (v, col, off) in enumerate([("月末引け(C-MOC)", BLUE, 0.17), ("現実的MOC(前日判定)", ORANGE, -0.17)]):
        g = win[(win.set == s) & (win["var"] == v)]
        y = len(sets6) - 1 - yi + off
        jit = (np.random.default_rng(1).random(len(g)) - 0.5) * 0.14
        ax.scatter(np.clip(g.lr * 100, -200, 200), y + jit, s=22, color=col, alpha=0.55, edgecolor="white", lw=0.5, zorder=3,
                   label=v if yi == 0 else None)
        fl = np.log(full.loc[v, s] / full.loc["3倍固定", s])
        ax.scatter([np.clip(fl * 100, -200, 200)], [y], marker="D", s=70, color=col, edgecolor=INK, lw=1.2, zorder=4,
                   label=("全期間（◆）" if (yi == 0 and k == 0) else None))
        w_ = WS[(WS.set == s) & (WS["var"] == v)].iloc[0]
        ax.text(205, y, f"勝{int(w_.w)}/負{int(w_.l)}" + (f"/分{int(w_.t)}" if w_.t else ""), va="center", fontsize=8.5, color=INK2)
    ylab.append(SHORT[s].replace("\n", " "))
ax.axvline(0, color=INK, lw=1)
ax.set_yticks(range(len(sets6))[::-1]); ax.set_yticklabels(ylab, fontsize=9)
ticks = [-200, -100, -50, 0, 50, 100, 200]
ax.set_xticks(ticks); ax.set_xticklabels([f"{np.expm1(t / 100) * 100:+.0f}%" for t in ticks])
ax.set_xlim(-210, 250); ax.grid(axis="x", alpha=0.25)
ax.set_xlabel("「翌営業日引け」比の税引後最終資産（対数目盛、点=10年窓 毎年1月開始、右端は窓の勝敗数）")
ax.axhspan(len(sets6) - 1.5, len(sets6) - 0.5, color="#f0efec", zorder=0)
ax.set_title("② 月末引け約定：作成期間(NDX)の+46%は、他の期間・指数では小さく符号もばらつく",
             loc="left", fontsize=12, fontweight="bold")
ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=3, frameon=False, fontsize=9)
ax.set_title(ax.get_title(loc="left"), loc="left", fontsize=12, fontweight="bold", pad=24)
fig.tight_layout(); fig.savefig(OUT / "fig6_月末引けOOS.png"); plt.close()

# fig7 2000年9月の紙一重
D_ = pd.read_pickle("data/daily_NDX.pkl"); mN = monthly_bars(D_).loc[:"2026-10"]; sN = O["sig"]["NDX"]
C = replace(base_cfg(*COST["NDX"]), start="1985-10", end="2026-10")
paths = {}
for lab, cfg, ex, col in [("翌営業日引け(C)", C, None, GRAY), ("月末引け・当日終値で判定(C-MOC)", replace(C, exec_lag=0, contrib_at_month_end=True), None, BLUE),
                          ("月末引け・前日終値で判定(現実的MOC)", replace(C, exec_lag=0, contrib_at_month_end=True), O["tm1"]["NDX"], ORANGE)]:
    r_, h_, _ = run(D_, sN, cfg, exec_dates=ex); paths[lab] = (h_.value_jpy.resample("ME").last(), col, r_["final_after_liq"])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5.4), dpi=110, gridspec_kw=dict(width_ratios=[2.3, 1]))
for lab, (v, col, fin) in paths.items():
    a1.plot(v.index, v.values, color=col, lw=2, label=f"{lab}  最終 {fin / 1e8:,.1f}億円")
a1.set_yscale("log"); a1.set_ylim(1e5, 3e10)
a1.yaxis.set_major_formatter(mt.FuncFormatter(lambda x, _: f"{x / 1e8:,.0f}億" if x >= 1e8 else f"{x / 1e4:,.0f}万"))
a1.axvline(pd.Timestamp("2000-09-29"), color=INK2, lw=0.8, ls=":")
a1.annotate("2000/9/29 売りシグナル\n（前日判定では出ない）", xy=(pd.Timestamp("2000-09-29"), 2e8), xytext=(pd.Timestamp("2004-01-01"), 2e7),
            fontsize=9, color=INK, arrowprops=dict(arrowstyle="->", color=INK2))
a1.legend(loc="upper left", frameon=False, fontsize=9); a1.grid(alpha=0.25)
a1.set_title("NDX(IS)の資産推移：判定日を1日ずらすだけで最終資産が約10分の1", loc="left", fontsize=11, fontweight="bold")
x = D_.loc["2000-09-18":"2000-09-29"]
a2.plot(x.index, x.c, color=INK, lw=2, marker="o", ms=5)
a2.scatter([x.index[-1]], [x.c.iloc[-1]], s=90, color=ORANGE, zorder=3, edgecolor="white", lw=1.5)
a2.annotate(f"最終日 {x.c.iloc[-1] / x.c.iloc[-2] - 1:+.1%}\nこの1日で売り成立", xy=(x.index[-1], x.c.iloc[-1]),
            xytext=(x.index[1], x.c.min() + 15), fontsize=9, arrowprops=dict(arrowstyle="->", color=INK2))
a2.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%m/%d")); a2.grid(alpha=0.25)
a2.set_title("NDX日次終値 2000年9月下旬", loc="left", fontsize=11, fontweight="bold")
fig.text(0.01, 0.01, "現実コストC・名目3万円/月、1985/10〜2026/10、円建て税引前評価額（凡例の最終値は清算後税引後）", fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT / "fig7_2000年9月の紙一重.png"); plt.close()
print("ok")
