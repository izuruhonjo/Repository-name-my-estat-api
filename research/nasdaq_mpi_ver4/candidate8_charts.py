"""候補8のグラフ（fig17〜19）。前提: python3 candidate8.py 実行済み"""
import sys
sys.path.insert(0, ".")
from candidate8 import *
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.ticker as mt
from matplotlib import font_manager
from matplotlib.lines import Line2D

font_manager.fontManager.addfont("/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf")
plt.rcParams.update({"font.family": "IPAGothic", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, GRAY, INK, INK2, GRID = "#2a78d6", "#eb6834", "#8a8984", "#0b0b0b", "#52514e", "#e4e3df"
R = pd.read_pickle("data/candidate8.pkl")["res"]
SETORDER = [s[0] for s in WSETS]
W = R[R.wtype == "10年窓"].groupby(["set", "start", "var"], sort=False)[["final", "D", "MAR"]].median()
SV = W.groupby(["set", "var"]).median()
SH = {s: s.replace(" ", "\n", 1) for s in SETORDER}; SH["NDX 1989-2026"] = "NDX\n1989-2026\n【IS】"
NW = W.xs("A", level="var").groupby("set").size()
LA, LB = "A 米ドルMMF・6%超→2倍", "B 全額すぐ1倍・3倍固定"

# ---------------------------------------------------------------- fig17: 判定（MAR中央値）
fig, ax = plt.subplots(figsize=(12, 5.6), dpi=110)
x = np.arange(len(SETORDER)); w = 0.3
h1 = [SV.loc[(s, "1倍保有"), "MAR"] for s in SETORDER]
for i, (v, c_) in enumerate((("A", BLUE), ("B", ORANGE))):
    y = [SV.loc[(s, v), "MAR"] for s in SETORDER]
    ax.bar(x + (i - 0.5) * (w + 0.03), y, width=w, color=c_, zorder=3)
    for xx, yy, hh in zip(x + (i - 0.5) * (w + 0.03), y, h1):
        ly = hh if (yy - 0.005 <= hh <= yy + 0.022) else yy          # 参考線と重なるときは線の上に値を書く
        ax.text(xx, ly + 0.006, f"{yy:.2f}", ha="center", va="bottom", fontsize=9, color=INK)
for xx, yy in zip(x, h1):
    ax.plot([xx - 0.36, xx + 0.36], [yy, yy], color=INK, lw=1.6, zorder=4)
UP = {s: ("A" if SV.loc[(s, "A"), "MAR"] > SV.loc[(s, "B"), "MAR"] else "B") for s in SETORDER}
ax.axvline(0.5, color=INK2, lw=1)
ax.set_xticks(x); ax.set_xticklabels([SH[s].replace("\n【IS】", "【IS】") + f"\n{UP[s]} が上（{NW[s]}窓）" for s in SETORDER], fontsize=9)
ax.tick_params(axis="x", length=0, pad=6); ax.set_ylim(0, 0.44)
ax.yaxis.grid(True, color=GRID, lw=1, zorder=0); ax.set_axisbelow(True); ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
ax.set_ylabel("MAR ＝ 税引後の年率 ÷ 最大下落率（大きいほど良い）")
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=BLUE), plt.Rectangle((0, 0), 1, 1, color=ORANGE), Line2D([0], [0], color=INK, lw=1.6)],
          labels=[LA, LB, "1倍を持ち続けた場合（参考）"], loc="upper right", frameon=False, fontsize=9)
ax.set_title("10年窓の判定：A が NDX と他5セット中3セットで上回り、採用。ただし3対2の小差で、ダウとラッセルは B が上",
             loc="left", fontsize=11.5, fontweight="bold")
fig.text(0.01, 0.01, "100万円一括・12か月線・現実コストC・税引後・円建て。各窓の値は締め日21通りの中央値、棒は窓の値の中央値。窓は重なっていて独立ではない",
         fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig("out/fig17_候補8_判定.png"); plt.close()

# ---------------------------------------------------------------- fig18: NDX の10年窓（開始年ごと）
a = W.xs("A", level="var").loc["NDX 1989-2026"]; b = W.xs("B", level="var").loc["NDX 1989-2026"]
yrs = np.array([int(s[:4]) for s in a.index])
fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 7.2), dpi=110, sharex=True, gridspec_kw=dict(height_ratios=[1.25, 1], hspace=0.12))
for ax in (a1, a2):
    ax.axvspan(1990.5, 2002.5, color="#f0efec", zorder=0)
    ax.yaxis.grid(True, color=GRID, lw=1, zorder=0); ax.set_axisbelow(True); ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
for v, c_, lab in ((a, BLUE, LA), (b, ORANGE, LB)):
    a1.plot(yrs, v.final / 1e4, color=c_, lw=2, marker="o", ms=6, mec="white", mew=1.2, label=lab, zorder=3)
    a2.plot(yrs, v.D * 100, color=c_, lw=2, marker="o", ms=6, mec="white", mew=1.2, zorder=3)
a1.set_yscale("log"); a1.set_yticks([10, 30, 100, 300, 1000, 3000, 10000])
a1.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:,.0f}")); a1.yaxis.set_minor_locator(mt.NullLocator())
a1.axhline(100, color=INK, lw=1); a1.text(2016.4, 108, "元本100万円", fontsize=8.5, color=INK2, ha="right", va="bottom")
a1.set_ylabel("10年後の税引後資産（万円、対数目盛）"); a1.legend(loc="upper right", frameon=False, fontsize=9, ncol=2)
a1.text(1996.5, 12.5, "2000〜02年の暴落を含む窓", fontsize=9, color=INK2, ha="center")
i0 = list(yrs).index(2000)
a1.annotate(f"A {a.final.iloc[i0] / 1e4:.0f}万円", (2000, a.final.iloc[i0] / 1e4), xytext=(2001.2, 36), fontsize=9, color=INK,
            arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
a1.annotate(f"B {b.final.iloc[i0] / 1e4:.0f}万円", (2000, b.final.iloc[i0] / 1e4), xytext=(2001.2, 19), fontsize=9, color=INK,
            arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
a2.set_ylim(-100, 0); a2.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
a2.set_ylabel("窓の中の最大下落率（円建て）"); a2.set_xlabel("窓の開始年（その年の1月に100万円を一括投資し、10年持つ）")
a2.set_xticks(range(1989, 2017, 3)); a2.set_xlim(1988.4, 2016.6)
a1.set_title("NDXの10年窓：暴落を含む窓では A が B の1.1〜4.1倍残り、含まない窓では B が A の1.1〜1.6倍。下落は28窓中20窓で A が浅い",
             loc="left", fontsize=11, fontweight="bold")
fig.text(0.01, 0.01, "100万円一括・12か月線・現実コストC・税引後・円建て。各点は締め日21通りの中央値。窓は重なっていて独立ではない", fontsize=8, color=INK2)
fig.subplots_adjust(left=0.08, right=0.985, top=0.94, bottom=0.1); fig.savefig("out/fig18_候補8_NDX窓.png"); plt.close()

# ---------------------------------------------------------------- fig19: 10年窓の最大下落率の分布（全セット）
fig, ax = plt.subplots(figsize=(12, 5.8), dpi=110)
yt, yl = [], []
for i, s in enumerate(SETORDER):
    for j, (v, c_) in enumerate((("A", BLUE), ("B", ORANGE))):
        y = -(i * 2.6 + j * 0.85); d = W.xs(v, level="var").loc[s].D * 100
        ax.scatter(d, np.full(len(d), y), s=46, color=c_, alpha=0.45, lw=0, zorder=3)
        m = d.median(); ax.plot([m, m], [y - 0.33, y + 0.33], color=INK, lw=2, zorder=4)
        ax.text(2, y, f"{m:.0f}%", fontsize=9, color=INK, va="center", ha="left")
    yt.append(-(i * 2.6 + 0.425)); yl.append(SH[s].replace("\n", " ").replace(" 【IS】", "【IS】") + f"\n（{NW[s]}窓）")
ax.set_yticks(yt); ax.set_yticklabels(yl, fontsize=9); ax.tick_params(axis="y", length=0)
ax.set_xlim(-100, 12); ax.set_xticks(range(-100, 1, 10)); ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.xaxis.grid(True, color=GRID, lw=1, zorder=0); ax.set_axisbelow(True); ax.spines["left"].set_visible(False)
ax.text(2, 0.75, "中央値", fontsize=8.5, color=INK2, ha="left")
ax.set_ylim(-(5 * 2.6 + 0.85) - 0.7, 1.2)
ax.legend(handles=[Line2D([0], [0], marker="o", ls="", color=BLUE, ms=7, alpha=0.6), Line2D([0], [0], marker="o", ls="", color=ORANGE, ms=7, alpha=0.6),
                   Line2D([0], [0], color=INK, lw=2)], labels=[LA, LB, "中央値"], loc="lower left", frameon=False, fontsize=9, ncol=3,
          bbox_to_anchor=(0.0, -0.17))
ax.set_xlabel("10年窓の中の最大下落率（円建て。1点＝1窓）")
ax.set_title("1985年以降の4セットでは、どちらの案も9割以上の窓で資産が一度は半分以下に。下落の中央値は6セット中5セットで A が浅い", loc="left", fontsize=11, fontweight="bold")
fig.text(0.01, 0.01, "100万円一括・12か月線・現実コストC。各点は締め日21通りの中央値。窓は重なっていて独立ではない", fontsize=8, color=INK2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig("out/fig19_候補8_最大下落率の分布.png"); plt.close()
print("charts ok")
