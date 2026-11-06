"""Excel(数式入り) と グラフを作成し、Python値とExcel数式値の突合用データを出力"""
import sys
sys.path.insert(0, ".")
from mpi import *
import xlsxwriter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

OUT = Path("./out"); OUT.mkdir(exist_ok=True)
font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams["font.family"] = "IPAGothic"

daily = pd.read_pickle("./data/daily.pkl")
m = monthly_bars(daily).loc[:"2026-10"]
s = signals(m)
cost3, cal3 = calibrate_cost(daily, "TQQQ", 3)
cost2, cal2 = calibrate_cost(daily, "QLD", 2)
res = pd.read_pickle("./data/results.pkl")
rob = pd.read_pickle("./data/robust.pkl")

A = Cfg(name="A 記事条件")
B = replace(A, name="B", lev_cost=cost3, financing=True, one_er=0.0015, dividends=True, exec_lag=1, contrib_at_month_end=False)
C = replace(B, name="C", commission=0.00495, comm_cap_usd=22, slippage=0.0002, fx=True, jp_tax=True, div_tax=True)
CM = replace(C, name="C-MOC", exec_lag=0, contrib_at_month_end=True)

# ---------------- A ledger (Python)
cA = replace(A, end="2022-08", infl_adj=True)
rA, hA, tA = run(daily, s, cA)
d = daily.loc["1985-10":"2022-08"]
r3 = lev_returns(d, 3.0, 0.0, False); r1 = d.r.values.copy()
r3[0] = 0; r1[0] = 0
g = pd.DataFrame({"f3": 1 + r3, "f1": 1 + r1}, index=d.index).groupby(d.index.to_period("M")).prod()
mv = hA.value_ccy.groupby(hA.index.to_period("M")).last()
led = pd.DataFrame({"f3": g.f3, "f1": g.f1, "sig": s.sig.loc["1985-10":"2022-08"], "py": mv})

# ---------------- C 年次税 (名目3万, 2026-10)
rC, hC, tC = run(daily, s, replace(C, end="2026-10", infl_adj=False))
taxlog = pd.DataFrame(rC["taxlog"])

# ---------------- 要因分解
steps = [("A 記事条件", A),
         ("+翌営業日約定・月初積立", replace(A, exec_lag=1, contrib_at_month_end=False)),
         ("+3倍の借入コスト(2×米短期金利)", replace(A, exec_lag=1, contrib_at_month_end=False, financing=True)),
         ("+配当込み化(1倍・3倍)", replace(A, exec_lag=1, contrib_at_month_end=False, financing=True, dividends=True)),
         ("+経費率等(3倍1.92%/1倍0.15%) =B", B),
         ("+SBI手数料0.495%/スリッページ0.02%", replace(B, commission=0.00495, comm_cap_usd=22, slippage=0.0002)),
         ("+為替(円建て評価)", replace(B, commission=0.00495, comm_cap_usd=22, slippage=0.0002, fx=True)),
         ("+日本税制(年内通算・3年繰越)", replace(B, commission=0.00495, comm_cap_usd=22, slippage=0.0002, fx=True, jp_tax=True)),
         ("+配当課税28.28% =C", C)]
attr = []
for end in ["2022-08", "2026-10"]:
    for infl in [True, False]:
        for lab, c in steps:
            dd = daily if c.dividends else daily.assign(dy=0.0)
            r, h, t = run(dd, s, replace(c, end=end, infl_adj=infl))
            attr.append(dict(end=end, infl=infl, step=lab, final=r["final_after_liq"], irr=r["irr"]))
attr = pd.DataFrame(attr)
attr.to_pickle("./data/attr.pkl")

# ---------------- 時系列 (名目3万, 1985-10〜2026-10)
series = {}
for lab, c in [("MPI 記事条件(A)", replace(A, end="2026-10", infl_adj=False)),
               ("MPI 現実コスト(C-MOC 月末引け)", replace(CM, end="2026-10", infl_adj=False)),
               ("MPI 現実コスト(C 翌営業日)", replace(C, end="2026-10", infl_adj=False)),
               ("TQQQ単純積立(C)", replace(C, end="2026-10", infl_adj=False, strategy="dca3")),
               ("QQQM単純積立(C)", replace(C, end="2026-10", infl_adj=False, strategy="dca1"))]:
    r, h, t = run(daily, s, c)
    series[lab] = h.value_jpy.resample("ME").last()
    contrib = h.contrib.resample("ME").last()
pd.to_pickle((series, contrib), "./data/series.pkl")

# ================================================================= Excel
wb = xlsxwriter.Workbook(str(OUT / "MPI_ver4_backtest.xlsx"))
F = dict(h=wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True, "valign": "top", "border": 1}),
         yen=wb.add_format({"num_format": "#,##0"}), oku=wb.add_format({"num_format": "#,##0.00"}),
         pct=wb.add_format({"num_format": "0.0%"}), pct2=wb.add_format({"num_format": "0.00%"}),
         f6=wb.add_format({"num_format": "0.000000"}), sci=wb.add_format({"num_format": "0.00E+00"}),
         title=wb.add_format({"bold": True, "font_size": 14}), b=wb.add_format({"bold": True}),
         wrap=wb.add_format({"text_wrap": True, "valign": "top"}),
         ok=wb.add_format({"bold": True, "font_color": "#006100", "bg_color": "#C6EFCE"}))

# --- 概要
ws = wb.add_worksheet("概要")
ws.set_column(0, 0, 34); ws.set_column(1, 8, 15)
ws.write(0, 0, "月足MACD&パラボリック投資法 ver.4.0 再現・現実コスト検証", F["title"])
ws.write(1, 0, "データ: Yahoo ^NDX(1985/10〜2026/11/5), TQQQ/QLD/QQQ実績, FRED DTB3(米3M T-bill), DEXJPUS(ドル円)。作成 2026-11-06")
hdr = ["期間終了", "積立額", "ケース", "戦略", "投入元本(円)", "最終資産 税引後(円)", "倍率", "IRR(年率)", "最大DD(時間加重)"]
for j, x in enumerate(hdr):
    ws.write(3, j, x, F["h"])
row = 4
lab_strat = {"mpi": "MPI ver4", "dca3": "TQQQ単純積立", "dca1": "QQQM単純積立"}
for _, x in res.iterrows():
    ws.write(row, 0, x.period); ws.write(row, 1, x.infl); ws.write(row, 2, x.case); ws.write(row, 3, lab_strat[x.strategy])
    ws.write_number(row, 4, x.contrib, F["yen"]); ws.write_number(row, 5, x.final_after_liq, F["yen"])
    ws.write_formula(row, 6, f"=F{row+1}/E{row+1}", F["oku"])
    ws.write_number(row, 7, x.irr, F["pct"]); ws.write_number(row, 8, x.mdd_twr, F["pct"])
    row += 1
ws.autofilter(3, 0, row - 1, 8); ws.freeze_panes(4, 0)

# --- 前提
ws = wb.add_worksheet("前提")
ws.set_column(0, 0, 30); ws.set_column(1, 1, 18); ws.set_column(2, 2, 90)
rows_ = [("項目", "値", "根拠・備考"),
         ("売買ルール", "ver4.0", "記事掲載PineScript(MPI)を移植: MACD(12,26,9)とPSAR(0.02,0.02,0.2)の同時条件。シグナルはNDX月足"),
         ("初回買シグナル", "1989-04", "記事「1989年4月から買いに入ります」と一致(移植検証)"),
         ("積立額(物価調整)", "30000*(11035/30000)^(k/442)", "記事表(1985/10=11,035円→2022/8=30,000円)を幾何補間。kは2022/8からの月数"),
         ("積立額(名目)", 30000, "毎月3万円固定"),
         ("3倍の日次リターン(記事)", "3×r_NDX価格", "記事の疑似レバ。金利・経費率なし"),
         ("3倍の日次リターン(現実)", "3×(r+配当) − 2×rf×dt/365 − c×dt/365", "c=実TQQQ(2010/2〜2026/11)のトータルリターンに一致するよう較正"),
         ("較正コスト c (TQQQ)", cal3["cost"], f"経費率+スワップスプレッド等。トラッキング誤差(年率) {cal3['tracking_err']:.2%}"),
         ("較正コスト c (QLD, 参考)", cal2["cost"], "2倍の参考値"),
         ("1倍(QQQM)経費率", 0.0015, "QQQMの経費率。1999/3以前の配当利回りは年0.4%と仮定、以降はQQQ実績"),
         ("SBI取引手数料", 0.00495, "約定代金の0.495%(税込)、上限22USD。SBI証券 米国株式ページ(2026-11-06取得)"),
         ("SBI ETFセレクション", "買付無料", "TQQQ/QQQMが対象かは未確認のため、保守的に全取引0.495%を適用"),
         ("為替コスト(基準)", 0, "リアルタイム為替取引は為替手数料無料(SBI公式)。外貨決済で売買し、ドルのまま保有"),
         ("為替コスト(感応度)", 0.25, "円貨決済の為替スプレッド25銭/USD(SBI公式)"),
         ("スリッページ", 0.0002, "片道0.02%(TQQQ/QQQMの売買スプレッド想定)"),
         ("譲渡益課税", TAX, "特定口座(源泉あり)。年内損益通算、確定申告で3年繰越控除を仮定。取得費は円建て移動平均"),
         ("配当課税", DIV_TAX, "米源泉10%+国内20.315%。外国税額控除は申告しない保守的前提"),
         ("NISA", "不使用", "TQQQ(レバレッジ型)は新NISA対象外。全取引を特定口座で計算"),
         ("約定(C)", "翌営業日終値", "月末確定シグナルを日本時間朝に確認→当日米国市場で約定"),
         ("約定(C-MOC)", "月末引け", "月末最終営業日の引け直前に判定し引け成行(MOC)で約定できた場合"),
         ("売却資金", "USD現金(無利息)", "売シグナル後は売却資金の1%(固定額)を毎月QQQMへ。現金は無利息(保守的)"),
         ]
for i, rr in enumerate(rows_):
    for j, x in enumerate(rr):
        if i == 0:
            ws.write(i, j, x, F["h"])
        elif isinstance(x, float):
            ws.write_number(i, j, x, F["pct2"])
        else:
            ws.write(i, j, x, F["wrap"])

# --- 較正
ws = wb.add_worksheet("較正_TQQQ")
ws.set_column(0, 0, 36); ws.set_column(1, 3, 16)
for j, x in enumerate(["項目", "TQQQ", "QLD"]):
    ws.write(0, j, x, F["h"])
t3 = load_yahoo("TQQQ"); t2 = load_yahoo("QLD")
items = [("開始日", cal3["start"], cal2["start"]), ("終了日", cal3["end"], cal2["end"]),
         ("開始時 調整後終値", t3.adj.iloc[0], t2.adj.iloc[0]), ("終了時 調整後終値", t3.adj.iloc[-1], t2.adj.iloc[-1]),
         ("年数", cal3["years"], cal2["years"])]
for i, (a, b, c_) in enumerate(items, start=1):
    ws.write(i, 0, a); ws.write(i, 1, b); ws.write(i, 2, c_)
ws.write(6, 0, "実績CAGR(数式)"); ws.write_formula(6, 1, "=(B5/B4)^(1/B6)-1", F["pct2"]); ws.write_formula(6, 2, "=(C5/C4)^(1/C6)-1", F["pct2"])
ws.write(7, 0, "較正後 疑似CAGR(Python)"); ws.write_number(7, 1, cal3["syn_cagr"], F["pct2"]); ws.write_number(7, 2, cal2["syn_cagr"], F["pct2"])
ws.write(8, 0, "記事方式(コスト無)疑似CAGR(Python)"); ws.write_number(8, 1, cal3["article_cagr"], F["pct2"]); ws.write_number(8, 2, cal2["article_cagr"], F["pct2"])
ws.write(9, 0, "記事方式の過大評価(年率, 数式)"); ws.write_formula(9, 1, "=B9-B7", F["pct2"]); ws.write_formula(9, 2, "=C9-C7", F["pct2"])
ws.write(10, 0, "較正コスト c(年率)"); ws.write_number(10, 1, cal3["cost"], F["pct2"]); ws.write_number(10, 2, cal2["cost"], F["pct2"])
ws.write(11, 0, "突合: 実績CAGR−疑似CAGR"); ws.write_formula(11, 1, "=B7-B8", F["sci"]); ws.write_formula(11, 2, "=C7-C8", F["sci"])

# --- A ledger (数式で再計算)
ws = wb.add_worksheet("A_数式再現")
ws.write(0, 0, "ケースA(記事条件・物価調整3万円・1985/10〜2022/8)を月次の数式だけで再計算し、Pythonと突合", F["b"])
cols = ["月", "k", "積立額", "シグナル", "3倍月次倍率", "1倍月次倍率", "前月レジーム(1=3倍)", "3倍評価(取引前)", "1倍評価(取引前)",
        "売り(3倍全売)", "買い(1倍→3倍)", "税", "取引後現金(暫定)", "レジーム", "毎月移管額(1%)", "3倍評価(取引後)", "3倍取得費(取引後)",
        "1倍評価(取引後)", "1倍取得費(取引後)", "現金(取引後)", "移管実行額", "3倍評価", "3倍取得費", "1倍評価", "1倍取得費", "現金",
        "総資産(Excel)", "総資産(Python)", "乖離率"]
for j, x in enumerate(cols):
    ws.write(2, j, x, F["h"])
ws.set_row(2, 45); ws.set_column(0, 0, 9); ws.set_column(1, 28, 13)
R0 = 3
for i, (per_, x) in enumerate(led.iterrows()):
    r = R0 + i; e = r + 1; p = r  # e: excel row number(1-based) ; p: previous row number
    first = i == 0
    P = (lambda col: "0") if first else (lambda col: f"{col}{p}")
    ws.write(r, 0, str(per_))
    ws.write_number(r, 1, (pd.Period("2022-08", "M") - per_).n)
    ws.write_formula(r, 2, f"=30000*(11035/30000)^(B{e}/442)", F["yen"])
    ws.write_number(r, 3, int(x.sig)); ws.write_number(r, 4, x.f3, F["f6"]); ws.write_number(r, 5, x.f1, F["f6"])
    ws.write_formula(r, 6, f"={P('N')}")
    ws.write_formula(r, 7, f"={P('V')}*E{e}", F["yen"])
    ws.write_formula(r, 8, f"={P('X')}*F{e}", F["yen"])
    ws.write_formula(r, 9, f"=IF(AND(D{e}=-1,G{e}=1),1,0)")
    ws.write_formula(r, 10, f"=IF(AND(D{e}=1,G{e}=0),1,0)")
    ws.write_formula(r, 11, f"=0.20315*(J{e}*MAX(0,H{e}-{P('W')})+K{e}*MAX(0,I{e}-{P('Y')}))", F["yen"])
    ws.write_formula(r, 12, f"={P('Z')}+J{e}*H{e}+K{e}*I{e}-L{e}", F["yen"])
    ws.write_formula(r, 13, f"=IF(J{e}=1,0,IF(K{e}=1,1,G{e}))")
    ws.write_formula(r, 14, f"=IF(J{e}=1,M{e}*0.01,{P('O')})", F["yen"])
    ws.write_formula(r, 15, f"=IF(J{e}=1,0,H{e}+K{e}*M{e})", F["yen"])
    ws.write_formula(r, 16, f"=IF(J{e}=1,0,{P('W')}+K{e}*M{e})", F["yen"])
    ws.write_formula(r, 17, f"=IF(K{e}=1,0,I{e})", F["yen"])
    ws.write_formula(r, 18, f"=IF(K{e}=1,0,{P('Y')})", F["yen"])
    ws.write_formula(r, 19, f"=IF(K{e}=1,0,M{e})", F["yen"])
    ws.write_formula(r, 20, f"=IF(AND(N{e}=0,T{e}>0),MIN(O{e},T{e}),0)", F["yen"])
    ws.write_formula(r, 21, f"=P{e}+IF(N{e}=1,C{e},0)", F["yen"])
    ws.write_formula(r, 22, f"=Q{e}+IF(N{e}=1,C{e},0)", F["yen"])
    ws.write_formula(r, 23, f"=R{e}+IF(N{e}=0,C{e},0)+U{e}", F["yen"])
    ws.write_formula(r, 24, f"=S{e}+IF(N{e}=0,C{e},0)+U{e}", F["yen"])
    ws.write_formula(r, 25, f"=T{e}-U{e}", F["yen"])
    ws.write_formula(r, 26, f"=V{e}+X{e}+Z{e}", F["yen"])
    ws.write_number(r, 27, x.py, F["yen"])
    ws.write_formula(r, 28, f"=AA{e}/AB{e}-1", F["sci"])
last = R0 + len(led)
ws.write(1, 0, "最大乖離率:", F["b"]); ws.write_formula(1, 1, f"=MAX(MAX(AC{R0+1}:AC{last}),-MIN(AC{R0+1}:AC{last}))", F["sci"])
ws.write(1, 3, "清算後(Excel):", F["b"]); ws.write_formula(1, 5, f"=AA{last}-0.20315*(MAX(0,V{last}-W{last})+MAX(0,X{last}-Y{last}))", F["yen"])
ws.write(1, 7, "清算後(Python):", F["b"]); ws.write_number(1, 9, rA["final_after_liq"], F["yen"])
ws.write(1, 11, "累計積立(Excel):", F["b"]); ws.write_formula(1, 13, f"=SUM(C{R0+1}:C{last})", F["yen"])
ws.write(1, 15, "累計積立(Python):", F["b"]); ws.write_number(1, 17, rA["contrib"], F["yen"])
ws.freeze_panes(3, 1)

# --- C 年次税
ws = wb.add_worksheet("C_年次税")
ws.write(0, 0, "ケースC MPI(名目3万円・1985/10〜2026/10) 特定口座の年次税計算を数式で検算", F["b"])
cols = ["年", "年間実現損益(円)", "源泉徴収(Python)", "源泉徴収(数式)", "繰越控除使用額", "還付(Python)", "還付(数式)", "年税額(数式)", "残り繰越損失", "検算差"]
for j, x in enumerate(cols):
    ws.write(2, j, x, F["h"])
ws.set_column(0, 9, 16)
for i, x in taxlog.iterrows():
    r = 3 + i; e = r + 1
    ws.write_number(r, 0, x.year); ws.write_number(r, 1, x.realized_gain, F["yen"]); ws.write_number(r, 2, x.withheld, F["yen"])
    ws.write_formula(r, 3, f"=0.20315*MAX(0,B{e})", F["yen"])
    ws.write_number(r, 4, x.cf_used, F["yen"]); ws.write_number(r, 5, x.refund, F["yen"])
    ws.write_formula(r, 6, f"=0.20315*E{e}", F["yen"])
    ws.write_formula(r, 7, f"=D{e}-G{e}", F["yen"])
    ws.write_number(r, 8, x.cf_left, F["yen"])
    ws.write_formula(r, 9, f"=ABS(C{e}-D{e})+ABS(F{e}-G{e})", F["yen"])
lt = 3 + len(taxlog)
ws.write(1, 0, "合計税額(数式):", F["b"]); ws.write_formula(1, 2, f"=SUM(H4:H{lt})", F["yen"])
ws.write(1, 4, "検算差合計:", F["b"]); ws.write_formula(1, 5, f"=SUM(J4:J{lt})", F["yen"])

# --- 要因分解
ws = wb.add_worksheet("要因分解")
ws.set_column(0, 1, 12); ws.set_column(2, 2, 38); ws.set_column(3, 5, 16)
for j, x in enumerate(["期間終了", "積立", "ステップ", "最終資産 税引後(円)", "前ステップ比(数式)", "A比(数式)", "IRR"]):
    ws.write(0, j, x, F["h"])
r = 1
for (end, infl), gdf in attr.groupby(["end", "infl"], sort=False):
    a_row = r + 1
    for k, (_, x) in enumerate(gdf.iterrows()):
        ws.write(r, 0, end); ws.write(r, 1, "物価調整" if infl else "名目3万"); ws.write(r, 2, x.step)
        ws.write_number(r, 3, x.final, F["yen"])
        if k > 0:
            ws.write_formula(r, 4, f"=D{r+1}/D{r}-1", F["pct"])
        ws.write_formula(r, 5, f"=D{r+1}/D{a_row}-1", F["pct"])
        ws.write_number(r, 6, x.irr, F["pct"])
        r += 1
    r += 1

# --- 頑健性
for name, key, colsk in [("開始年感応度", "start", ["start", "strat", "contrib", "final", "irr", "mdd"]),
                         ("パラメータ感応度", "param", ["psar_max", "macd", "cfg", "final", "irr", "mdd", "trades"]),
                         ("約定方式", "exec", ["exec", "infl", "final", "irr", "mdd", "trades"])]:
    ws = wb.add_worksheet(name)
    dfk = rob[key]
    ws.set_column(0, len(colsk) + 1, 16)
    for j, x in enumerate(colsk + (["倍率(数式)"] if "contrib" in colsk else [])):
        ws.write(0, j, x, F["h"])
    for i, (_, x) in enumerate(dfk.iterrows()):
        for j, cn in enumerate(colsk):
            v = x[cn]
            fmt = F["pct"] if cn in ("irr", "mdd") else (F["yen"] if cn in ("final", "contrib") else None)
            if isinstance(v, (bool, np.bool_)):
                ws.write(i + 1, j, "物価調整" if v else "名目3万")
            elif isinstance(v, (int, float, np.integer, np.floating)):
                ws.write_number(i + 1, j, float(v), fmt)
            else:
                ws.write(i + 1, j, str(v))
        if "contrib" in colsk:
            ws.write_formula(i + 1, len(colsk), f"=D{i+2}/C{i+2}", F["oku"])
    ws.autofilter(0, 0, len(dfk), len(colsk) - 1)

# --- シグナル
ws = wb.add_worksheet("シグナル")
for j, x in enumerate(["月", "NDX月末終値", "MACD", "シグナル線", "PSAR", "売買(+1買/-1売)"]):
    ws.write(0, j, x, F["h"])
ws.set_column(0, 5, 14)
ev = s[s.sig != 0]
for i, (per_, x) in enumerate(ev.iterrows()):
    ws.write(i + 1, 0, str(per_)); ws.write_number(i + 1, 1, x.c); ws.write_number(i + 1, 2, x.macd); ws.write_number(i + 1, 3, x.signal)
    ws.write_number(i + 1, 4, x.psar); ws.write_number(i + 1, 5, int(x.sig))
wb.close()
print("excel written")
print("A python final", rA["final_after_liq"], "contrib", rA["contrib"])
print("C taxlog rows", len(taxlog), "total tax python", rC["tax_paid"])
