"""候補7の Excel（数式で判定・突合）とグラフ。前提: python3 candidate7.py 実行済み"""
import sys
sys.path.insert(0, ".")
from candidate7 import *
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name as CN
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.ticker as mt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams.update({"font.family": "IPAGothic", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, AQUA, GRAY, INK, INK2 = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984", "#0b0b0b", "#52514e"
O = pd.read_pickle("data/candidate7.pkl"); R = O["res"].reset_index(drop=True); COST = O["cost"]
S = pd.read_pickle("data/simple_rules.pkl")["res"]
SETORDER = [s[0] for s in SETS2]; MODEL = list(MODES); LEVN = list(LEVS)
VARS = [(e, l) for e in EXITS for l in LEVN]
MED = R.groupby(["mode", "exit", "lev", "set"]).final.median()
H3 = S[S.rule == "3倍保有"].set_index(["mode", "set"]).final
K0 = S[(S.rule == "MPI(ver4.0)") & (S.k == 0)].set_index(["mode", "set"]).final


def beats(mode, a, b):
    """a=(exit,lev) が b を上回るセット（中央値）"""
    return {s: bool(MED[(mode, *a, s)] > MED[(mode, *b, s)]) for s in SETORDER}


DEC = {}
for mode in MODEL:
    st1 = {}
    for e in EXITS[1:]:
        w = beats(mode, (e, "3倍固定"), ("drip", "3倍固定"))
        st1[e] = (w[SETORDER[0]] and sum(w[s] for s in SETORDER[1:]) >= 4, sum(w[s] for s in SETORDER[1:]), MED[(mode, e, "3倍固定", SETORDER[0])])
    ok = [e for e in st1 if st1[e][0]]
    ex = max(ok, key=lambda e: (st1[e][1], st1[e][2])) if ok else "drip"
    w2 = beats(mode, (ex, "6%超→2倍"), (ex, "3倍固定"))
    lv = "6%超→2倍" if (w2[SETORDER[0]] and sum(w2[s] for s in SETORDER[1:]) >= 4) else "3倍固定"
    DEC[mode] = dict(st1=st1, exit=ex, w2=w2, n2=sum(w2[s] for s in SETORDER[1:]), lev=lv)
    print(mode, {e: v[:2] for e, v in st1.items()}, "→", ex, "| 2倍:", DEC[mode]["n2"], "→", lv)

wb = xlsxwriter.Workbook("out/MPI_ver4_候補7_置き場と2倍.xlsx", {"use_future_functions": True})
F = dict(h=wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True, "border": 1}),
         yen=wb.add_format({"num_format": "#,##0"}), man=wb.add_format({"num_format": "#,##0"}), x2=wb.add_format({"num_format": "0.00"}),
         pct=wb.add_format({"num_format": "0.0%"}), b=wb.add_format({"bold": True}), t=wb.add_format({"bold": True, "font_size": 14}),
         sci=wb.add_format({"num_format": "0.00E+00"}), d=wb.add_format({"num_format": "yyyy-mm-dd"}),
         wrap=wb.add_format({"text_wrap": True, "valign": "top"}))
ws0 = wb.add_worksheet("判定"); wsd = wb.add_worksheet("検証設計"); wd = wb.add_worksheet("データ")
cols = ["資金", "セット", "置き場", "レバ", "締め日k", "税引後最終資産(円)", "IRR", "最大DD", "売買回数", "2倍への乗換回数"]
for j, c in enumerate(cols): wd.write(0, j, c, F["h"])
for i, x in enumerate(R.itertuples(), start=1):
    wd.write(i, 0, x.mode); wd.write(i, 1, x.set); wd.write(i, 2, x.exit); wd.write(i, 3, x.lev); wd.write_number(i, 4, x.k)
    wd.write_number(i, 5, x.final, F["yen"]); wd.write_number(i, 6, x.irr, F["pct"]); wd.write_number(i, 7, x.mdd, F["pct"])
    wd.write_number(i, 8, x.trades); wd.write_number(i, 9, x.n_switch)
N = len(R) + 1; Dc = lambda c: f"データ!${c}$2:${c}${N}"
wd.autofilter(0, 0, N - 1, 9); wd.freeze_panes(1, 4)
ws = ws0; ws.set_column(0, 0, 34); ws.set_column(1, 9, 13)
ws.write(0, 0, "候補7: 12か月線 × 売った後の置き場 × 高金利時の2倍（100万円スタート）", F["t"])
ws.write(1, 0, "現実コストC・税引後・締め日21通りの中央値（万円）。判定は事前に決めた手順を数式で実行")
r = 3; CHK = []; DECROW = {}
for mode in MODEL:
    ws.write(r, 0, f"【{mode}】 中央値（万円, 数式）", F["b"]); r += 1
    ws.write(r, 0, "置き場 / レバ", F["h"]); ws.write(r, 1, "", F["h"])
    for j, s in enumerate(SETORDER): ws.write(r, j + 2, s, F["h"])
    hr = r + 1; r += 1; rowof = {}
    for e, l in VARS:
        ws.write(r, 0, e); ws.write(r, 1, l); rowof[(e, l)] = r + 1
        for j, s in enumerate(SETORDER):
            c = CN(j + 2)
            cond = f'({Dc("A")}="{mode}")*({Dc("B")}={c}${hr})*({Dc("C")}=$A{r + 1})*({Dc("D")}=$B{r + 1})'
            ws.write_array_formula(r, j + 2, r, j + 2, f"{{=MEDIAN(IF({cond},{Dc('F')}))/1E4}}", F["man"])
            CHK.append((r, j + 2, MED[(mode, e, l, s)] / 1e4))
        r += 1
    for lab_, src in [("参考: 3倍保有（万円）", H3), ("参考: K0＝MPI月末締め（万円）", K0)]:
        ws.write(r, 0, lab_)
        for j, s in enumerate(SETORDER): ws.write_number(r, j + 2, src[(mode, s)] / 1e4, F["man"])
        rowof[lab_] = r + 1; r += 1
    r += 1
    ws.write(r, 0, "手順1: dripより良いセット（OOS 6セット中の数）", F["b"]); ws.write(r, 1, "IS(NDX)も良い"); ws.write(r, 2, "合格(数式)"); r += 1
    base = rowof[("drip", "3倍固定")]
    for e in EXITS[1:]:
        rr = rowof[(e, "3倍固定")]
        ws.write(r, 0, e)
        ws.write_formula(r, 3, "=" + "+".join(f"IF({CN(j + 2)}{rr}>{CN(j + 2)}{base},1,0)" for j in range(1, len(SETORDER))))
        ws.write_formula(r, 1, f"=C{rr}>C{base}")
        ws.write_formula(r, 2, f"=AND(B{r + 1},D{r + 1}>=4)")
        r += 1
    p1 = r - len(EXITS) + 2
    ws.write(r, 0, "→ 選ばれた置き場(Python)"); ws.write(r, 1, DEC[mode]["exit"]); DECROW[(mode, "exit")] = r + 1; r += 1
    ex = DEC[mode]["exit"]; ra, rb = rowof[(ex, "6%超→2倍")], rowof[(ex, "3倍固定")]
    ws.write(r, 0, f"手順2: {ex}で 2倍切替 が3倍固定より良いOOSセット数(数式)", F["b"])
    ws.write_formula(r, 3, "=" + "+".join(f"IF({CN(j + 2)}{ra}>{CN(j + 2)}{rb},1,0)" for j in range(1, len(SETORDER))))
    ws.write_formula(r, 1, f"=C{ra}>C{rb}"); ws.write_formula(r, 2, f"=AND(B{r + 1},D{r + 1}>=4)")
    ws.write(r, 4, "Python"); ws.write_number(r, 5, DEC[mode]["n2"]); DECROW[(mode, "n2")] = r + 1; r += 1
    fin = rowof[(ex, DEC[mode]["lev"])]
    ws.write(r, 0, f"保険料: 最終({ex}・{DEC[mode]['lev']}) ÷ 3倍保有（数式）", F["b"])
    for j in range(len(SETORDER)):
        c = CN(j + 2); ws.write_formula(r, j + 2, f"={c}{fin}/{c}{rowof['参考: 3倍保有（万円）']}", F["x2"])
    r += 1
    ws.write(r, 0, f"最終 ÷ K0（数式）", F["b"])
    for j in range(len(SETORDER)):
        c = CN(j + 2); ws.write_formula(r, j + 2, f"={c}{fin}/{c}{rowof['参考: K0＝MPI月末締め（万円）']}", F["x2"])
    r += 2
ws.write(r, 0, "Pythonとの最大|差|（中央値, 万円）", F["b"])
assert len(CHK) <= 250
ws.write_formula(r, 1, "=MAX(" + ",".join(f"ABS({CN(c)}{rr + 1}-{float(v)!r})" for rr, c, v in CHK) + ")", F["sci"])
SUMROW = r + 1
ws.freeze_panes(3, 2)
rows_ = [("項目", "内容"),
         ("シグナル", "12か月線（月末の終値 > 12か月平均なら3倍を保有）。締め日21通り(k=-10〜+10)、7セット"),
         ("資金", "主=100万円一括・積立なし、感応度=100万円+月3万円。現実コストC、締め日の翌営業日の引けで約定"),
         ("置き場", "drip=現金→毎月1%ずつ1倍(ver4.0と同じ、基準) / cash=全額USD現金(金利0) / mmf=全額米ドルMMF(米3M金利−年0.3%、分配に毎日20.315%課税) / one=全額すぐ1倍"),
         ("レバ", "3倍固定 / 6%超→2倍（米3M金利が6%超の月は2倍に乗換え。前回OOS検証でISから選んだ規則をそのまま）"),
         ("手順1(事前固定)", "dripと比べて21通り中央値が IS と OOS 6セット中4以上で上回れば合格。複数なら勝ちセット数→IS中央値で1つ選ぶ"),
         ("手順2(事前固定)", "手順1の置き場で、2倍切替が3倍固定を同じ基準で上回れば採用"),
         ("保険料", "最終の組合せ ÷ 3倍保有。1未満なら全損回避のために払ったコスト"),
         ("限界", "MMFの為替差損益は非課税扱い（簡略化）。MMF分配は株の損失と通算しない保守的な扱い。手順は最終資産だけで判定し、最大DDは判定に入れていない")]
wsd.set_column(0, 0, 18); wsd.set_column(1, 1, 120)
for i, rr_ in enumerate(rows_):
    for j, x in enumerate(rr_): wsd.write(i, j, x, F["h"] if i == 0 else F["wrap"])

# ------------------------------------------------------------------ 数式検算: 12か月線シグナル（日次生データから）+ mmf / one の日次台帳
DN = pd.read_pickle("data/daily_NDX.pkl"); ND = len(DN) + 1
sig12 = O["sig"][0]; NB = len(sig12)
SN = "検算_12か月線"; ws = wb.add_worksheet(SN)
for j, c in enumerate(["日付", "終値", "月末(数式)", "月末累計(数式)", "足番号(数式)"]): ws.write(0, j, c, F["h"])
for i, (dt_, x) in enumerate(DN.iterrows()):
    r_ = i + 2
    ws.write_datetime(i + 1, 0, dt_.to_pydatetime(), F["d"]); ws.write_number(i + 1, 1, x.c)
    ws.write_formula(i + 1, 2, f"=IF(MONTH(A{r_ + 1})<>MONTH(A{r_}),1,0)" if i < len(DN) - 1 else "=1")
    ws.write_formula(i + 1, 3, f"=C{r_}" if i == 0 else f"=D{r_ - 1}+C{r_}")
    ws.write_formula(i + 1, 4, "=0" if i == 0 else f"=D{r_ - 1}")
bc = ["足#", "終値(数式)", "12か月平均", "状態", "前の状態", "シグナル(数式)", "シグナル(Py)", "一致"]
for j, c in enumerate(bc): ws.write(0, 6 + j, c, F["h"])
G = f"$E$2:$E${ND}"
for j in range(NB):
    r_ = j + 2; p = r_ - 1
    ws.write_number(j + 1, 6, j)
    ws.write_formula(j + 1, 7, f'=INDEX($B$2:$B${ND},COUNTIF({G},"<="&G{r_}))')
    if j >= 11:
        ws.write_formula(j + 1, 8, f"=AVERAGE(H{r_ - 11}:H{r_})"); ws.write_formula(j + 1, 9, f"=IF(H{r_}>I{r_},1,0)")
    else:
        ws.write(j + 1, 9, "")
    ws.write_formula(j + 1, 10, "=0" if j == 0 else f'=IF(J{p}="",K{p},J{p})')
    ws.write_formula(j + 1, 11, f'=IF(J{r_}="",0,IF(J{r_}<>K{r_},IF(J{r_}=1,1,-1),0))')
    ws.write_number(j + 1, 12, int(sig12.sig.iloc[j])); ws.write_formula(j + 1, 13, f"=IF(L{r_}=M{r_},1,0)")
NBr = NB + 1
ws.write(1, 15, "シグナル不一致数(数式)", F["b"]); ws.write_formula(1, 16, f"=COUNT(G2:G{NBr})-SUM(N2:N{NBr})")
c3 = COST["NDX"][0]
dd = DN.loc["1989-01-01":"2026-10-31"]; off = DN.index.get_loc(dd.index[0])
LED = {}
for mode_ in ["mmf", "one"]:
    cfgL = Cfg(name="ledger", lev_cost=c3, financing=True, one_er=0.0015, dividends=True, exec_lag=1, contrib_at_month_end=False,
               tax_on=False, infl_adj=False, start="1989-01", end=END, initial=INITIAL, monthly=0.0, exit_mode=mode_)
    rL, hL = run_rule(DN, sig12, cfgL)
    nm = f"検算_台帳_{mode_}"; ws = wb.add_worksheet(nm)
    LC = ["日付", "r", "暦日数", "米3M金利", "1倍配当(日)", "3倍日次", "1倍日次", "月初", "約定シグナル", "3倍 成長後", "1倍 成長後",
          "現金(MMF)成長後", "売実行", "買実行", "状態", "現金 約定後", "3倍 約定後", "1倍 約定後", "1倍(全額移動後)", "現金(移動後)", "投入額",
          "3倍 期末", "1倍 期末", "現金 期末", "総資産(数式)", "総資産(Python)", "乖離率"]
    for j, c in enumerate(LC): ws.write(0, j, c, F["h"])
    prm = [("c3", c3), ("1倍経費率", 0.0015), ("MMF手数料", 0.003), ("初期投資", INITIAL), ("置き場", mode_)]
    for i, (t, v) in enumerate(prm):
        ws.write(i, 28, t); (ws.write_number if isinstance(v, float) else ws.write)(i, 29, v)
    ws.write(5, 28, "開始時の状態(数式)"); ws.write_formula(5, 29, f"=INDEX({SN}!$K$2:$K${NBr},{SN}!E{off + 2}+1)")
    ws.write(6, 28, "開始時の状態(Py)"); ws.write(6, 29, init_regime(sig12, "1989-01"))
    for i, (dt_, x) in enumerate(dd.iterrows()):
        r_ = i + 2; p = r_ - 1; sr = off + 2 + i
        pv = (lambda c: "0") if i == 0 else (lambda c: f"{c}{p}")
        reg = "$AD$6" if i == 0 else f"O{p}"
        ws.write_formula(i + 1, 0, f"={SN}!A{sr}", F["d"])
        ws.write_formula(i + 1, 1, f"={SN}!B{sr}/{SN}!B{sr - 1}-1")
        ws.write_number(i + 1, 2, x["dt"]); ws.write_number(i + 1, 3, x["rf"]); ws.write_number(i + 1, 4, x["dy"])
        ws.write_formula(i + 1, 5, f"=3*(B{r_}+E{r_})-2*D{r_}*C{r_}/365-$AD$1*C{r_}/365")
        ws.write_formula(i + 1, 6, f"=B{r_}-$AD$2*C{r_}/365")
        ws.write_formula(i + 1, 7, "=1" if i == 0 else f"=IF(MONTH(A{r_})<>MONTH(A{p}),1,0)")
        ws.write_formula(i + 1, 8, "=0" if i == 0 else f"=IF({SN}!E{sr}<>{SN}!E{sr - 1},INDEX({SN}!$L$2:$L${NBr},{SN}!E{sr - 1}+1),0)")
        ws.write_formula(i + 1, 9, f"={pv('V')}*(1+F{r_})")
        ws.write_formula(i + 1, 10, f"={pv('W')}*(1+G{r_})*(1+E{r_})")
        ws.write_formula(i + 1, 11, f'=IF($AD$5="mmf",{pv("X")}*(1+MAX(D{r_}-$AD$3,0)*C{r_}/365),{pv("X")})')
        ws.write_formula(i + 1, 12, f"=AND(I{r_}=-1,{reg}=1)"); ws.write_formula(i + 1, 13, f"=AND(I{r_}=1,{reg}=0)")
        ws.write_formula(i + 1, 14, f"=IF(M{r_},0,IF(N{r_},1,{reg}))")
        ws.write_formula(i + 1, 15, f"=IF(M{r_},L{r_}+J{r_},IF(N{r_},0,L{r_}))")
        ws.write_formula(i + 1, 16, f"=IF(M{r_},0,IF(N{r_},J{r_}+L{r_}+K{r_},J{r_}))")
        ws.write_formula(i + 1, 17, f"=IF(N{r_},0,K{r_})")
        ws.write_formula(i + 1, 18, f'=R{r_}+IF(AND(M{r_},$AD$5="one"),P{r_},0)')
        ws.write_formula(i + 1, 19, f'=IF(AND(M{r_},$AD$5="one"),0,P{r_})')
        ws.write_formula(i + 1, 20, "=$AD$4" if i == 0 else "=0")
        ws.write_formula(i + 1, 21, f"=Q{r_}+IF(O{r_}=1,U{r_},0)")
        ws.write_formula(i + 1, 22, f'=S{r_}+IF(AND(O{r_}=0,$AD$5="one"),U{r_},0)')
        ws.write_formula(i + 1, 23, f'=T{r_}+IF(AND(O{r_}=0,$AD$5="mmf"),U{r_},0)')
        ws.write_formula(i + 1, 24, f"=V{r_}+W{r_}+X{r_}", F["yen"])
        ws.write_number(i + 1, 25, hL.value_ccy.iloc[i], F["yen"])
        ws.write_formula(i + 1, 26, f"=Y{r_}/Z{r_}-1", F["sci"])
    NL = len(dd) + 1
    ws.write(8, 28, "最大|乖離率|", F["b"]); ws.write_array_formula(8, 29, 8, 29, f"{{=MAX(ABS(AA2:AA{NL}))}}", F["sci"])
    ws.write(9, 28, "最終(数式)"); ws.write_formula(9, 29, f"=Y{NL}", F["yen"])
    ws.write(10, 28, "最終(Python)"); ws.write_number(10, 29, rL["final_pre_liq"], F["yen"])
    ws.freeze_panes(1, 1)
    LED[mode_] = nm
wb.close()
pd.to_pickle(dict(SUMROW=SUMROW, DECROW=DECROW, DEC={m: (DEC[m]["exit"], DEC[m]["n2"], DEC[m]["lev"]) for m in MODEL}, LED=LED),
             "data/candidate7_report.pkl")
print("excel ok")

# ================================================================= グラフ
SH = {s: s.replace(" ", "\n", 1) for s in SETORDER}; SH["NDX 1989-2026"] = "NDX\n1989-2026\n【IS】"
LM = "一括100万"
# fig15: 8通り ÷ 基準(drip・3倍固定)
labels = [f"{EXN[e]}・{l}" for e, l in VARS]
M = np.array([[MED[(LM, e, l, s)] / MED[(LM, "drip", "3倍固定", s)] for s in SETORDER] for e, l in VARS]); L = np.log2(M)
cmap = LinearSegmentedColormap.from_list("div", ["#d03b3b", "#f0efec", BLUE])
fig, ax = plt.subplots(figsize=(12, 5.8), dpi=110)
im = ax.imshow(np.clip(L, -1.5, 1.5), cmap=cmap, vmin=-1.5, vmax=1.5, aspect="auto")
mddv = R[R["mode"] == LM].groupby(["exit", "lev", "set"]).mdd.median()
for i, (e, l) in enumerate(VARS):
    for j, s in enumerate(SETORDER):
        ax.text(j, i, f"{M[i, j]:.2f}倍\nDD{mddv[(e, l, s)]:.0%}", ha="center", va="center", fontsize=8,
                color="white" if abs(L[i, j]) > 1.1 else INK)
ax.set_xticks(range(len(SETORDER))); ax.set_xticklabels([SH[s] for s in SETORDER], fontsize=9)
ax.set_yticks(range(len(VARS))); ax.set_yticklabels(labels, fontsize=9)
for i, (e, l) in enumerate(VARS):
    if (e, l) == (DEC[LM]["exit"], DEC[LM]["lev"]): ax.get_yticklabels()[i].set_fontweight("bold")
ax.axvline(0.5, color=INK, lw=1.5)
for y in (1.5, 3.5, 5.5): ax.axhline(y, color="white", lw=2)
ax.tick_params(length=0); [s_.set_visible(False) for s_ in ax.spines.values()]
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, ticks=[-1, 0, 1]); cb.ax.set_yticklabels(["1/2倍", "基準", "2倍"])
ax.set_title("100万円一括・12か月線：売った後は「全額すぐ1倍」が全7セットで基準より良い。ただしNDXの最大DDは−85%→−95%",
             loc="left", fontsize=11, fontweight="bold")
fig.text(0.01, 0.01, "締め日21通りの税引後最終資産の中央値 ÷ 基準（現金→毎月1%ずつ1倍・3倍固定）。DD=最大ドローダウンの中央値（時間加重）。現実コストC",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig("out/fig15_候補7_置き場と2倍.png"); plt.close()

# fig16: 保険料（÷3倍保有）— K0・12か月線(基準)・最終案・MMF案
fig, ax = plt.subplots(figsize=(12, 5.4), dpi=110)
fx_ = DEC[LM]["exit"], DEC[LM]["lev"]
series = [("K0（MPI・月末締め）", lambda s: K0[(LM, s)], ORANGE),
          ("12か月線・基準（現金→1%ずつ1倍）", lambda s: MED[(LM, "drip", "3倍固定", s)], GRAY),
          ("12か月線・全額 米ドルMMF・6%超→2倍", lambda s: MED[(LM, "mmf", "6%超→2倍", s)], AQUA),
          (f"12か月線・{EXN[fx_[0]]}・{fx_[1]}（手順で選ばれた案）", lambda s: MED[(LM, *fx_, s)], BLUE)]
w = 0.2
for i, (nm, f_, c_) in enumerate(series):
    v = [f_(s) / H3[(LM, s)] for s in SETORDER]
    xs = np.arange(len(SETORDER)) + (i - 1.5) * w
    ax.bar(xs, v, width=w * 0.92, color=c_, label=nm, edgecolor="white", lw=0.8)
    if i == 3:
        for x_, y_ in zip(xs, v):
            if y_ < 3.4: ax.text(x_, y_ + 0.06, f"{y_:.2f}", ha="center", fontsize=8, color=INK)
        ndx_sel = v[0]
ax.axhline(1, color=INK, lw=1); ax.text(len(SETORDER) - 0.45, 1.04, "3倍保有と同じ", fontsize=8.5, color=INK2, ha="right")
ax.set_ylim(0, 3.5); ax.set_xticks(range(len(SETORDER))); ax.set_xticklabels([SH[s] for s in SETORDER], fontsize=9)
ax.text(0.55, 3.25, f"← NDXは上端で切断：全案が3倍保有の4.6〜16倍（選ばれた案は{ndx_sel:.1f}倍）", fontsize=8.5, color=INK2, ha="left")
ax.legend(loc="upper right", frameon=False, fontsize=8.5); ax.grid(axis="y", alpha=0.25)
ax.set_ylabel("÷ 3倍保有（1未満＝保険料を払っている）")
ax.set_title("保険料：選ばれた案は7セット中4で3倍保有を上回り、保険料はダウ・ラッセル・NDX 2022以降だけに縮小", loc="left", fontsize=11, fontweight="bold")
fig.text(0.01, 0.01, "100万円一括・現実コストC・税引後。12か月線系は締め日21通りの中央値、K0と3倍保有は月末締め/締め日に依存しない値", fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig("out/fig16_候補7_保険料.png"); plt.close()
print("charts ok")
