"""候補ルール vs K0（MPI ver4.0・月末締め＝記事どおりの運用）。前提: simple_rules.py 実行済み
  比較1: 候補も月末締め(k=0)にした同条件の比較（÷K0）
  比較2: 候補の締め日21通りのうち K0 を上回る数（候補側の締め日運に左右されないか）"""
import sys
sys.path.insert(0, ".")
from simple_rules import *
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name as CN
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams.update({"font.family": "IPAGothic", "font.size": 10})
BLUE, INK, INK2 = "#2a78d6", "#0b0b0b", "#52514e"
O = pd.read_pickle("data/simple_rules.pkl"); R = O["res"].reset_index(drop=True)
SETORDER = [s[0] for s in SETS2]; CAND = RULES[1:] + list(BENCH); MODEL = list(MODES)
K0 = R[(R.rule == "MPI(ver4.0)") & (R.k == 0)].set_index(["mode", "set"]).final
A = R[R.k == 0].set_index(["mode", "set", "rule"])
RAT = {(m, s, ru): A.loc[(m, s, ru)].final / K0[(m, s)] for m in MODEL for s in SETORDER for ru in CAND}
WIN = {(m, s, ru): int((R[(R["mode"] == m) & (R.set == s) & (R.rule == ru)].final > K0[(m, s)]).sum())
       for m in MODEL for s in SETORDER for ru in RULES[1:]}

wb = xlsxwriter.Workbook("out/MPI_ver4_候補vsK0.xlsx")
F = dict(h=wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True, "border": 1}),
         yen=wb.add_format({"num_format": "#,##0"}), x2=wb.add_format({"num_format": "0.00"}), pct=wb.add_format({"num_format": "0.0%"}),
         b=wb.add_format({"bold": True}), t=wb.add_format({"bold": True, "font_size": 14}), sci=wb.add_format({"num_format": "0.00E+00"}))
ws0 = wb.add_worksheet("比較"); wd = wb.add_worksheet("データ")
cols = ["資金", "セット", "ルール", "締め日k", "税引後最終資産(円)", "IRR", "最大DD", "売買回数"]
for j, c in enumerate(cols): wd.write(0, j, c, F["h"])
for i, x in enumerate(R.itertuples(), start=1):
    wd.write(i, 0, x.mode); wd.write(i, 1, x.set); wd.write(i, 2, x.rule); wd.write_number(i, 3, x.k)
    wd.write_number(i, 4, x.final, F["yen"]); wd.write_number(i, 5, x.irr, F["pct"]); wd.write_number(i, 6, x.mdd, F["pct"]); wd.write_number(i, 7, x.trades)
N = len(R) + 1
D = lambda c: f"データ!${c}$2:${c}${N}"
ws = ws0; ws.set_column(0, 0, 34); ws.set_column(1, 7, 14)
ws.write(0, 0, "候補ルール vs K0（MPI ver4.0・月末締め＝記事どおりの運用）", F["t"])
ws.write(1, 0, "現実コストC・税引後。すべて「データ」シートからSUMIFS/COUNTIFSで計算")
r = 3; CHK = []
for m in MODEL:
    ws.write(r, 0, f"【{m}】 K0の税引後最終資産（円）", F["b"])
    for j, s in enumerate(SETORDER): ws.write(r - 1 if False else r + 1, j + 1, s, F["h"])
    ws.write(r + 1, 0, "セット", F["h"]); hr = r + 2
    ws.write(r + 2, 0, "K0 = MPI・月末締め(数式)")
    for j, s in enumerate(SETORDER):
        c = CN(j + 1)
        ws.write_formula(r + 2, j + 1, f'=SUMIFS({D("E")},{D("A")},"{m}",{D("B")},{c}${hr},{D("C")},"MPI(ver4.0)",{D("D")},0)', F["yen"])
    k0r = r + 3; r += 4
    ws.write(r, 0, "比較1: 候補も月末締め ÷ K0（数式）", F["b"]); r += 1
    for ru in CAND:
        ws.write(r, 0, ru)
        for j, s in enumerate(SETORDER):
            c = CN(j + 1)
            ws.write_formula(r, j + 1, f'=SUMIFS({D("E")},{D("A")},"{m}",{D("B")},{c}${hr},{D("C")},$A{r + 1},{D("D")},0)/{c}${k0r}', F["x2"])
            CHK.append((r, j + 1, RAT[(m, s, ru)]))
        r += 1
    ws.write(r, 0, "比較2: 候補の締め日21通りのうちK0を上回る数（数式）", F["b"]); r += 1
    for ru in RULES[1:]:
        ws.write(r, 0, ru)
        for j, s in enumerate(SETORDER):
            c = CN(j + 1)
            ws.write_formula(r, j + 1, f'=COUNTIFS({D("A")},"{m}",{D("B")},{c}${hr},{D("C")},$A{r + 1},{D("E")},">"&{c}${k0r})')
            CHK.append((r, j + 1, WIN[(m, s, ru)]))
        r += 1
    r += 1
ws.write(r, 0, "Pythonとの最大|差|", F["b"])
ws.write_formula(r, 1, "=MAX(" + ",".join(f"ABS({CN(c)}{rr + 1}-{float(v)!r})" for rr, c, v in CHK[:250]) + ")", F["sci"])
if len(CHK) > 250:
    ws.write_formula(r, 2, "=MAX(" + ",".join(f"ABS({CN(c)}{rr + 1}-{float(v)!r})" for rr, c, v in CHK[250:]) + ")", F["sci"])
wb.close()
pd.to_pickle(dict(row=r + 1, n=len(CHK)), "data/k0_report.pkl")

# 図: 100万円一括、比較1（÷K0）+ 比較2（勝数）
m = "一括100万"
M = np.array([[RAT[(m, s, ru)] for s in SETORDER] for ru in CAND]); L = np.log2(M)
cmap = LinearSegmentedColormap.from_list("div", ["#d03b3b", "#f0efec", BLUE])
fig, ax = plt.subplots(figsize=(11.5, 5.6), dpi=110)
im = ax.imshow(np.clip(L, -2, 2), cmap=cmap, vmin=-2, vmax=2, aspect="auto")
for i, ru in enumerate(CAND):
    for j, s in enumerate(SETORDER):
        t = f"{M[i, j]:.2f}倍" + (f"\n21通り中{WIN[(m, s, ru)]}" if ru in RULES else "")
        ax.text(j, i, t, ha="center", va="center", fontsize=8.5, color="white" if abs(L[i, j]) > 1.4 else INK)
SH = {s: s.replace(" ", "\n", 1) for s in SETORDER}; SH["NDX 1989-2026"] = "NDX\n1989-2026\n【IS】"
ax.set_xticks(range(len(SETORDER))); ax.set_xticklabels([SH[s] for s in SETORDER], fontsize=9)
ax.set_yticks(range(len(CAND))); ax.set_yticklabels(CAND, fontsize=9.5)
ax.axvline(0.5, color=INK, lw=1.5); ax.axhline(4.5, color=INK, lw=1.2)
ax.tick_params(length=0); [s_.set_visible(False) for s_ in ax.spines.values()]
cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01, ticks=[-2, -1, 0, 1, 2])
cb.ax.set_yticklabels(["1/4倍", "1/2倍", "K0と同じ", "2倍", "4倍"])
ax.set_title("100万円一括：候補（月末締め）÷ K0（MPI・月末締め）。12か月線はダウ以外の6セットでK0以上",
             loc="left", fontsize=11.5, fontweight="bold")
fig.text(0.01, 0.01, "上段=税引後最終資産の倍率（両方とも月末締め）。下段『21通り中n』=候補の締め日21通りのうちK0を上回った数。下2行は締め日に依存しない参考",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig("out/fig14_候補vsK0.png"); plt.close()
print("ok", len(CHK))
