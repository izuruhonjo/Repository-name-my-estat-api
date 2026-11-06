"""
S2改良検証のExcel突合ブック（Pythonの結果を、生データからExcel数式で独立に再計算して照合）
  1) 日次NAV → 年率・ソルティノ・最大下落・前半/後半の年率（S2・K0・C1・K1・L10、換金後NAVも）
  2) 月末の持ち物と繰越損失 → 潜在税・換金後NAV（S2）
  3) QQQ・金の日次終値 → 20日ボラ・ブレーキ判定・有事判定
  4) 年別リターンと差
  5) 48通りの勝ち数
  6) DSR（月次の超過リターン29本から）
  7) 世帯の5年窓（2021-11〜2026-10、目標ルール＋DC④、11/6実額起点）
使い方: python3 build_excel_imp.py  → out_imp/S2改良検証_Excel突合.xlsx
"""
import sys, json, math
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as L
import imp_common as C, imp_candidates as K, s2x as X, s2engine as E, hh

w = C.World("data")
allc = {c["code"]: c for c in K.CANDIDATES + K.COMBOS}
SER = ["S2", "K0", "C1", "K1", "L10"]
runs = {"S2": w.run({}, None)}
for k in SER[1:]:
    c = allc[k]; runs[k] = w.run(c["cfg"], c["policy"], jkey=c["judg"])
snapS2 = X.simulate_x(w.mkt, w.assets, w.judg["base"], X.XCfg(), w.ctx["base"], snapshots=True)["snaps"]
bold = Font(bold=True); hl = PatternFill("solid", fgColor="FFF2CC")
wb = Workbook()
checks = []   # (説明, シート名, セル(式), Python値)

# ---------------- 1) 日次NAVと指標 ----------------
ws = wb.active; ws.title = "日次NAV"
navs = {k: runs[k]["nav"] for k in SER}
navs["S2換金後"] = runs["S2"]["nav_liq"]; navs["K0換金後"] = runs["K0"]["nav_liq"]
names = list(navs)
dates = navs["S2"].index
n = len(dates); R0 = 3; Rl = R0 + n - 1
ws.cell(1, 1, "日付").font = bold
for j, nm in enumerate(names):
    base = 2 + j * 4
    ws.cell(1, base, nm).font = bold
    for t, h in enumerate(["NAV(Python)", "日次リターン(式)", "下落日だけ(式)", "高値からの下落(式)"]):
        ws.cell(2, base + t, h)
for r, d in enumerate(dates):
    R = R0 + r
    ws.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    for j, nm in enumerate(names):
        b = 2 + j * 4; cN, cR, cNeg, cDD = L(b), L(b + 1), L(b + 2), L(b + 3)
        ws.cell(R, b, float(navs[nm].iloc[r]))
        if r > 0:
            ws.cell(R, b + 1, f"={cN}{R}/{cN}{R-1}-1")
            ws.cell(R, b + 2, f'=IF({cR}{R}<0,{cR}{R},"")')
        ws.cell(R, b + 3, f"={cN}{R}/MAX({cN}${R0}:{cN}{R})-1" if r < 2 else f"={cN}{R}/MAX({cN}{R},{cN}{R-1}/(1+{cDD}{R-1}))-1")
# 集計シート
ss = wb.create_sheet("指標の突合")
hdr = ["系列", "年率(式)", "年率(Python)", "ソルティノ(式)", "ソルティノ(Python)", "最大下落(式)", "最大下落(Python)",
       "前半年率(式)", "前半年率(Python)", "後半年率(式)", "後半年率(Python)", "最大差", "一致"]
for j, h in enumerate(hdr, 1):
    ss.cell(1, j, h).font = bold
ss.cell(1, 15, "前半の終わり（行）"); ss.cell(1, 16, f"=MATCH(DATE(2012,12,31),日次NAV!A{R0}:A{Rl},1)+{R0-1}")
for j, nm in enumerate(names):
    R = 2 + j
    b = 2 + j * 4; cN, cNeg, cDD = L(b), L(b + 2), L(b + 3)
    m = X.indicators(navs[nm]); h1 = X.indicators(X.sub(navs[nm], *C.TRAIN)); h2 = X.indicators(X.sub(navs[nm], *C.TEST))
    ss.cell(R, 1, nm)
    cagr = f"(日次NAV!{cN}{Rl}/日次NAV!{cN}{R0})^(365.25/(日次NAV!A{Rl}-日次NAV!A{R0}))-1"
    ss.cell(R, 2, "=" + cagr); ss.cell(R, 3, float(m["CAGR"]))
    ss.cell(R, 4, f"=({cagr})/(STDEV(日次NAV!{cNeg}{R0+1}:{cNeg}{Rl})*SQRT(252))"); ss.cell(R, 5, float(m["Sortino"]))
    ss.cell(R, 6, f"=MIN(日次NAV!{cDD}{R0}:{cDD}{Rl})"); ss.cell(R, 7, float(m["MaxDD"]))
    e1 = "$P$1"
    ss.cell(R, 8, f"=(INDEX(日次NAV!{cN}:{cN},{e1})/日次NAV!{cN}{R0})^(365.25/(INDEX(日次NAV!A:A,{e1})-日次NAV!A{R0}))-1"); ss.cell(R, 9, float(h1["CAGR"]))
    ss.cell(R, 10, f"=(日次NAV!{cN}{Rl}/INDEX(日次NAV!{cN}:{cN},{e1}+1))^(365.25/(日次NAV!A{Rl}-INDEX(日次NAV!A:A,{e1}+1)))-1"); ss.cell(R, 11, float(h2["CAGR"]))
    ss.cell(R, 12, f"=MAX(ABS(B{R}-C{R}),ABS(D{R}-E{R}),ABS(F{R}-G{R}),ABS(H{R}-I{R}),ABS(J{R}-K{R}))")
    ss.cell(R, 13, f"=IF(L{R}<1E-9,1,0)")
    checks.append((f"指標 {nm}", "指標の突合", f"L{R}", 0.0))

# ---------------- 2) 月末の潜在税（S2） ----------------
st = wb.create_sheet("潜在税_S2")
assets_ = ["GP", "N1", "SV"]
hdr = ["月末", "現金", "入金待ち", "繰越損失(使える分)"] + [f"{a}{x}" for a in assets_ for x in ("口数", "取得額", "価格")] + \
      ["評価額(式)", "含み益(式)", "潜在税(式)", "換金後(式)", "評価額(Python)", "潜在税(Python)", "差(評価額)", "差(潜在税)"]
for j, h in enumerate(hdr, 1):
    st.cell(1, j, h).font = bold
for r, row in enumerate(snapS2.itertuples(index=False), start=2):
    st.cell(r, 1, row.date.to_pydatetime()).number_format = "yyyy-mm-dd"
    st.cell(r, 2, float(row.cash)); st.cell(r, 3, float(row.pending)); st.cell(r, 4, float(row.losses))
    col = 5
    for a in assets_:
        st.cell(r, col, float(getattr(row, f"{a}_units"))); st.cell(r, col + 1, float(getattr(row, f"{a}_cost"))); st.cell(r, col + 2, float(getattr(row, f"{a}_px")))
        col += 3
    # 列：E..M が 3資産×3
    val = "+".join(f"{L(5+3*k)}{r}*{L(7+3*k)}{r}" for k in range(3))
    gain = "+".join(f"({L(5+3*k)}{r}*{L(7+3*k)}{r}-{L(6+3*k)}{r})" for k in range(3))
    st.cell(r, 14, f"=B{r}+C{r}+{val}")
    st.cell(r, 15, f"={gain}")
    st.cell(r, 16, f"=MAX(O{r}-D{r},0)*{E.TAX}")
    st.cell(r, 17, f"=N{r}-P{r}")
    st.cell(r, 18, float(row.nav)); st.cell(r, 19, float(row.latent))
    st.cell(r, 20, f"=N{r}-R{r}"); st.cell(r, 21, f"=P{r}-S{r}")
last = 1 + len(snapS2)
st.cell(1, 23, "最大差(評価額・円)"); st.cell(1, 24, f"=MAX(MAX(T2:T{last}),-MIN(T2:T{last}))")
st.cell(2, 23, "最大差(潜在税・円)"); st.cell(2, 24, f"=MAX(MAX(U2:U{last}),-MIN(U2:U{last}))")
checks.append(("潜在税 評価額の最大差(円)", "潜在税_S2", "X1", 0.0)); checks.append(("潜在税 潜在税の最大差(円)", "潜在税_S2", "X2", 0.0))

# ---------------- 3) ボラ・有事判定 ----------------
sv = wb.create_sheet("ボラ・有事判定")
mk = w.mkt[(w.mkt.index >= "1999-12-01") & (w.mkt.index <= "2026-10-31")]
rv = E.realized_vol(w.mkt["qqq"]).reindex(mk.index)
g20 = (w.mkt["gold"] / w.mkt["gold"].shift(20) - 1).reindex(mk.index)
q20 = (w.mkt["qqq"] / w.mkt["qqq"].shift(20) - 1).reindex(mk.index)
hdr = ["日付", "QQQ", "金(ドル)", "対数リターン(式)", "20日ボラ(式)", "ブレーキ条件(式)", "金20日(式)", "QQQ20日(式)", "有事条件(式)",
       "20日ボラ(Python)", "ブレーキ(Python)", "有事(Python)", "ボラ差", "判定の不一致"]
for j, h in enumerate(hdr, 1):
    sv.cell(1, j, h).font = bold
for r, (d, row) in enumerate(mk.iterrows(), start=2):
    sv.cell(r, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    sv.cell(r, 2, float(row.qqq)); sv.cell(r, 3, float(row.gold))
    if r > 2:
        sv.cell(r, 4, f"=LN(B{r}/B{r-1})")
    if r >= 23:
        sv.cell(r, 5, f"=STDEV(D{r-19}:D{r})*SQRT(252)")
        sv.cell(r, 6, f"=IF(E{r}>=0.3,1,0)")
        sv.cell(r, 7, f"=C{r}/C{r-20}-1"); sv.cell(r, 8, f"=B{r}/B{r-20}-1")
        sv.cell(r, 9, f"=IF(AND(G{r}>=0.07,H{r}<=-0.05),1,0)")
        v = rv.loc[d]
        sv.cell(r, 10, float(v)); sv.cell(r, 11, int(v >= 0.30)); sv.cell(r, 12, int((g20.loc[d] >= 0.07) and (q20.loc[d] <= -0.05)))
        sv.cell(r, 13, f"=ABS(E{r}-J{r})"); sv.cell(r, 14, f"=ABS(F{r}-K{r})+ABS(I{r}-L{r})")
lastv = 1 + len(mk)
sv.cell(1, 16, "ボラの最大差"); sv.cell(1, 17, f"=MAX(M23:M{lastv})")
sv.cell(2, 16, "判定の不一致(日数)"); sv.cell(2, 17, f"=SUM(N23:N{lastv})")
sv.cell(3, 16, "ブレーキ条件の日数(式)"); sv.cell(3, 17, f"=SUM(F23:F{lastv})")
sv.cell(4, 16, "有事条件の日数(式)"); sv.cell(4, 17, f"=SUM(I23:I{lastv})")
checks.append(("ボラの最大差", "ボラ・有事判定", "Q1", 0.0)); checks.append(("判定の不一致(日数)", "ボラ・有事判定", "Q2", 0.0))

# ---------------- 4) 年別 ----------------
sy = wb.create_sheet("年別")
years = list(range(2000, 2027))
sy.cell(1, 1, "年").font = bold
for j, nm in enumerate(SER):
    sy.cell(1, 2 + j, f"{nm} 年末NAV(式)").font = bold
    sy.cell(1, 2 + len(SER) + j, f"{nm} 年リターン(式)").font = bold
for j, nm in enumerate(SER[1:]):
    sy.cell(1, 2 + 2 * len(SER) + j, f"{nm}−S2(式)").font = bold
    sy.cell(1, 2 + 2 * len(SER) + len(SER) - 1 + j, f"{nm}−S2(Python)").font = bold
py_y = {}
for nm in SER:
    nv = navs[nm]; ye = nv.resample("YE").last()
    ret = ye.pct_change(); ret.iloc[0] = ye.iloc[0] / nv.iloc[0] - 1
    py_y[nm] = ret
for r, y in enumerate(years, start=2):
    sy.cell(r, 1, y)
    for j, nm in enumerate(SER):
        cN = L(2 + SER.index(nm) * 4)
        sy.cell(r, 2 + j, f"=LOOKUP(DATE({y},12,31),日次NAV!$A${R0}:$A${Rl},日次NAV!{cN}${R0}:{cN}${Rl})")
        prev = f"日次NAV!{cN}${R0}" if r == 2 else f"{L(2+j)}{r-1}"
        sy.cell(r, 2 + len(SER) + j, f"={L(2+j)}{r}/{prev}-1")
    for j, nm in enumerate(SER[1:]):
        cc = 2 + 2 * len(SER) + j
        sy.cell(r, cc, f"={L(2+len(SER)+j+1)}{r}-{L(2+len(SER))}{r}")
        sy.cell(r, cc + len(SER) - 1, float(py_y[nm].iloc[r - 2] - py_y["S2"].iloc[r - 2]))
c0 = 2 + 2 * len(SER); c1 = c0 + len(SER) - 2; p0 = c0 + len(SER) - 1; p1 = p0 + len(SER) - 2
sy.cell(1, p1 + 2, "最大差"); sy.cell(1, p1 + 3, f"=SUMPRODUCT(MAX(ABS({L(c0)}2:{L(c1)}{len(years)+1}-{L(p0)}2:{L(p1)}{len(years)+1})))")
checks.append(("年別リターン差の最大差", "年別", f"{L(p1+3)}1", 0.0))

# ---------------- 5) 48通り ----------------
sg = wb.create_sheet("48通り")
g = pd.read_csv("out_imp/grid48.csv"); gs = pd.read_csv("out_imp/grid48_summary.csv", index_col=0)
gcols = ["code", "start", "cost", "lag", "dCAGR", "dL_CAGR", "MaxDD", "MaxDD_S2", "L_MaxDD", "L_MaxDD_S2"]
for j, h in enumerate(gcols, 1):
    sg.cell(1, j, h).font = bold
for r, row in enumerate(g[gcols].itertuples(index=False), start=2):
    for j, v in enumerate(row, 1):
        sg.cell(r, j, v if isinstance(v, str) else float(v))
lg = 1 + len(g)
hdr = ["候補", "年率で勝ち(式)", "年率で勝ち(Python)", "換金後で勝ち(式)", "換金後で勝ち(Python)", "最大下落が悪化(式)", "最大下落が悪化(Python)",
       "換金後の最大下落が悪化(式)", "換金後(Python)", "年率差の平均(式)", "年率差の平均(Python)", "不一致"]
for j, h in enumerate(hdr, 12):
    sg.cell(1, j, h).font = bold
for r, code in enumerate(gs.index, start=2):
    sg.cell(r, 12, code)
    rng = f"$A$2:$A${lg}"
    sg.cell(r, 13, f'=COUNTIFS({rng},L{r},$E$2:$E${lg},">0")'); sg.cell(r, 14, int(gs.loc[code, "年率で勝ち"]))
    sg.cell(r, 15, f'=COUNTIFS({rng},L{r},$F$2:$F${lg},">0")'); sg.cell(r, 16, int(gs.loc[code, "換金後で勝ち"]))
    sg.cell(r, 17, f"=SUMPRODUCT(({rng}=L{r})*($G$2:$G${lg}<$H$2:$H${lg}-1E-9))"); sg.cell(r, 18, int(gs.loc[code, "最大下落が悪化"]))
    sg.cell(r, 19, f"=SUMPRODUCT(({rng}=L{r})*($I$2:$I${lg}<$J$2:$J${lg}-1E-9))"); sg.cell(r, 20, int(gs.loc[code, "換金後の最大下落が悪化"]))
    sg.cell(r, 21, f"=AVERAGEIF({rng},L{r},$E$2:$E${lg})"); sg.cell(r, 22, float(gs.loc[code, "年率差の平均"]))
    sg.cell(r, 23, f"=ABS(M{r}-N{r})+ABS(O{r}-P{r})+ABS(Q{r}-R{r})+ABS(S{r}-T{r})+ABS(U{r}-V{r})")
lr = 1 + len(gs)
sg.cell(lr + 2, 12, "不一致の合計"); sg.cell(lr + 2, 13, f"=SUM(W2:W{lr})")
checks.append(("48通りの不一致合計", "48通り", f"M{lr+2}", 0.0))

# ---------------- 6) DSR ----------------
sd = wb.create_sheet("DSR")
M = pd.read_csv("out_imp/monthly_all.csv", index_col=0, parse_dates=True)
trials = [c for c in M.columns if c not in ("S2元", "S2")]
Mx = M[trials].sub(M["S2"], axis=0).dropna()
pdsr = json.load(open("out_imp/pbo_dsr.json"))
T_ = len(Mx); N_ = len(trials)
sd.cell(1, 1, "月").font = bold
for j, c in enumerate(trials, 2):
    sd.cell(1, j, c).font = bold
for r, (d, row) in enumerate(Mx.iterrows(), start=2):
    sd.cell(r, 1, d.strftime("%Y-%m"))
    for j, c in enumerate(trials, 2):
        sd.cell(r, j, float(row[c]))
lm = 1 + T_
rS = lm + 2
sd.cell(rS, 1, "月次SR(式)").font = bold
for j in range(2, 2 + N_):
    cl = L(j)
    sd.cell(rS, j, f"=AVERAGE({cl}2:{cl}{lm})/STDEV({cl}2:{cl}{lm})")
sd.cell(rS + 1, 1, "SRの分散(式)"); sd.cell(rS + 1, 2, f"=VAR({L(2)}{rS}:{L(1+N_)}{rS})")
sd.cell(rS + 2, 1, "試行数N"); sd.cell(rS + 2, 2, N_)
sd.cell(rS + 3, 1, "月数T"); sd.cell(rS + 3, 2, T_)
sd.cell(rS + 4, 1, "SR0(式)"); sd.cell(rS + 4, 2, f"=SQRT(B{rS+1})*((1-0.5772156649)*NORMSINV(1-1/B{rS+2})+0.5772156649*NORMSINV(1-1/(B{rS+2}*EXP(1))))")
rD = rS + 6
for j, h in enumerate(["候補", "SR(式)", "歪度(式)", "尖度(式)", "DSR(式)", "DSR(Python)", "差"], 1):
    sd.cell(rD, j, h).font = bold
for k, code in enumerate(["K0", "P1", "C1", "K1", "C2", "C5", "C6", "T1", "L10", "L20"]):
    R = rD + 1 + k
    cl = L(2 + trials.index(code)); rng = f"{cl}2:{cl}{lm}"
    sd.cell(R, 1, code)
    sd.cell(R, 2, f"={cl}{rS}")
    sd.cell(R, 3, f"=SUMPRODUCT(({rng}-AVERAGE({rng}))^3)/COUNT({rng})/(STDEVP({rng})^3)")
    sd.cell(R, 4, f"=SUMPRODUCT(({rng}-AVERAGE({rng}))^4)/COUNT({rng})/(STDEVP({rng})^4)")
    sd.cell(R, 5, f"=NORMSDIST((B{R}-$B${rS+4})*SQRT($B${rS+3}-1)/SQRT(1-C{R}*B{R}+(D{R}-1)/4*B{R}^2))")
    sd.cell(R, 6, float(pdsr["dsr"][f"{code}|N={N_}"]))
    sd.cell(R, 7, f"=ABS(E{R}-F{R})")
sd.cell(rD, 9, "最大差"); sd.cell(rD, 10, f"=MAX(G{rD+1}:G{rD+10})")
checks.append(("DSRの最大差", "DSR", f"J{rD}", 0.0))

# ---------------- 7) 世帯の5年窓 ----------------
for code in ["S2", "K0"]:
    hw = wb.create_sheet(f"世帯5年窓_{code}")
    r_ = runs[code]
    _, T = C.household(w, r_["nav"], r_["states"])
    k0 = len(T) - 60
    kw = dict(dc_col=C.D1, cS2=0, cN=50_000, W0=C.W0, D0=C.D0, N0=C.N0)
    P = hh.hh_mc(T, start_idx=[k0], return_paths=True, **kw)
    sub = T.iloc[k0:k0 + 60]
    params = [("W0", C.W0), ("D0", C.D0), ("N0", C.N0), ("cS2", 0), ("cDC", 27_500), ("cN", 50_000), ("目標", 1e8), ("lo", 0.85),
              ("hi", 1.15), ("遅れL", 2.5), ("先行L", 1.2), ("到達L", 0.5), ("基本L", 2.0), ("TQQQ追加コスト", 0.03)]
    for i, (k, v) in enumerate(params, start=1):
        hw.cell(i, 14, k); hw.cell(i, 15, float(v))
    hdr = ["月", "S2月次", "×フラグ", "金利(年)", "DC月次", "NISA月次", "世帯(月初)", "必要経路", "到達度F", "濃さL", "S2実効リターン", "S2残高", "DC残高", "NISA残高", "世帯(月末)"]
    for j, h in enumerate(hdr, 1):
        hw.cell(18, j, h).font = bold
    H0c = "($O$1+$O$2+$O$3)"
    for t, (d, rr) in enumerate(sub.iterrows()):
        R = 19 + t
        hw.cell(R, 1, d.strftime("%Y-%m")); hw.cell(R, 2, float(rr["S2"])); hw.cell(R, 3, float(rr["RET"])); hw.cell(R, 4, float(rr["RATE"]))
        hw.cell(R, 5, float(rr[C.D1])); hw.cell(R, 6, float(rr["A_FANG"]))
        pW = "$O$1" if t == 0 else f"L{R-1}"; pD = "$O$2" if t == 0 else f"M{R-1}"; pN = "$O$3" if t == 0 else f"N{R-1}"
        hw.cell(R, 7, f"={pW}+{pD}+{pN}")
        hw.cell(R, 8, f"={H0c}*($O$7/{H0c})^({t}/60)")
        hw.cell(R, 9, f"=G{R}/H{R}")
        hw.cell(R, 10, f"=IF(G{R}>=$O$7,$O$12,IF(I{R}<$O$8,$O$10,IF(I{R}>$O$9,$O$11,$O$13)))")
        hw.cell(R, 11, f"=IF(C{R}>0.5,B{R},(J{R}/2)*B{R}-(MAX(J{R}-1,0)-J{R}/2)*D{R}/12-MAX(J{R}-2,0)*$O$14/12)")
        hw.cell(R, 12, f"=({pW}+$O$4)*(1+K{R})")
        hw.cell(R, 13, f"=({pD}+$O$5)*(1+E{R})")
        hw.cell(R, 14, f"=({pN}+$O$6)*(1+F{R})")
        hw.cell(R, 15, f"=L{R}+M{R}+N{R}")
    last = 19 + 59
    hw.cell(1, 17, "最終 世帯(式)"); hw.cell(1, 18, f"=O{last}")
    hw.cell(2, 17, "最終 世帯(Python)"); hw.cell(2, 18, float(P["H"][0]))
    hw.cell(3, 17, "一度でも1億(式)"); hw.cell(3, 18, f"=IF(MAX(O19:O{last})>=$O$7,1,0)")
    hw.cell(4, 17, "一度でも1億(Python)"); hw.cell(4, 18, int(P["hit"][0]))
    hw.cell(5, 17, "差(円)"); hw.cell(5, 18, "=R1-R2")
    checks.append((f"世帯5年窓 {code} 最終の差(円)", f"世帯5年窓_{code}", "R5", 0.0))
    checks.append((f"世帯5年窓 {code} 1億到達の一致", f"世帯5年窓_{code}", "R3", float(P["hit"][0])))

# ---------------- 目次 ----------------
s0 = wb.create_sheet("突合の結果", 0)
s0.cell(1, 1, "S2改良検証 Excel突合（LibreOfficeで再計算した値をPythonと照合）").font = bold
s0.cell(3, 1, "項目").font = bold; s0.cell(3, 2, "シート").font = bold; s0.cell(3, 3, "式の結果").font = bold; s0.cell(3, 4, "期待値").font = bold; s0.cell(3, 5, "判定").font = bold
for i, (lbl, sh, cell, exp) in enumerate(checks, start=4):
    s0.cell(i, 1, lbl); s0.cell(i, 2, sh); s0.cell(i, 3, f"='{sh}'!{cell}"); s0.cell(i, 4, exp)
    s0.cell(i, 5, f'=IF(ABS(C{i}-D{i})<=MAX(1E-6,ABS(D{i})*1E-9),"一致","不一致")')
wb.save("out_imp/S2改良検証_Excel突合.xlsx")
json.dump(checks, open("out_imp/excel_checks.json", "w"), ensure_ascii=False)
print("saved", len(checks), "checks")
