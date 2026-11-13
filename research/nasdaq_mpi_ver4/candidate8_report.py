"""候補8の Excel（数式で窓の値・セットの値・判定を再計算）。前提: python3 candidate8.py 実行済み。図は candidate8_charts.py"""
import sys
sys.path.insert(0, ".")
from candidate8 import *
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name as CN

O = pd.read_pickle("data/candidate8.pkl"); R = O["res"].reset_index(drop=True); COST = O["cost"]
R["MARu"] = R.R / R.mdd_usd.abs()
SETORDER = [s[0] for s in WSETS]; IS, OOS = SETORDER[0], SETORDER[1:]
KIND = {s[0]: s[1] for s in SETS2}
ALLV = list(VARS) + REFS                      # A, B, A', B', 基準, K0, 3倍保有, 1倍保有
MET = [("F", "final"), ("D", "D"), ("MAR", "MAR")]
TIE = 1e-9                                    # 窓ごとの勝ち負け: 相対差がこれ以下なら「同じ」（計算誤差を勝ち負けに数えない）


# ------------------------------------------------------------------ Python 側の集計
def winvals(df, cols=("final", "R", "D", "MAR", "mdd_usd", "MARu")):
    """窓の値 = 締め日21通りの中央値"""
    return df.groupby(["set", "start", "end", "var"], sort=False)[list(cols)].median()


def decide(W, col="MAR", dcol="D"):
    """W: index=(set,start,end,var)。事前登録の主判定とタイブレーク"""
    sv = W.groupby(["set", "var"])[[col, dcol]].median()
    up = {s: ("A" if sv.loc[(s, "A"), col] > sv.loc[(s, "B"), col] else "B" if sv.loc[(s, "B"), col] > sv.loc[(s, "A"), col] else "同じ") for s in SETORDER}
    sh = {s: ("A" if sv.loc[(s, "A"), dcol] > sv.loc[(s, "B"), dcol] else "B" if sv.loc[(s, "B"), dcol] > sv.loc[(s, "A"), dcol] else "同じ") for s in SETORDER}
    nA, nB = sum(up[s] == "A" for s in OOS), sum(up[s] == "B" for s in OOS)
    main = "A" if (up[IS] == "A" and nA >= 3) else "B" if (up[IS] == "B" and nB >= 3) else "優劣なし"
    dA, dB = sum(v == "A" for v in sh.values()), sum(v == "B" for v in sh.values())
    final = main if main != "優劣なし" else ("A" if dA > dB else "B" if dB > dA else "A(据え置き)")
    return dict(sv=sv, up=up, sh=sh, nA=nA, nB=nB, main=main, dA=dA, dB=dB, final=final)


W10 = winvals(R[R.wtype == "10年窓"]); W5 = winvals(R[R.wtype == "5年窓"]); WM = winvals(R[R.wtype == "10年窓+月3万"])
WK0 = R[(R.wtype == "10年窓") & (R.k == 0)].set_index(["set", "start", "end", "var"])[["final", "R", "D", "MAR"]]
DEC = dict(main=decide(W10), k0=decide(WK0), usd=decide(W10, "MARu", "mdd_usd"), y5=decide(W5), m3=decide(WM))
for k_, v in DEC.items():
    print(k_, "MAR上:", v["up"], "| OOS A", v["nA"], "B", v["nB"], "| 主判定", v["main"], "| D浅い A", v["dA"], "B", v["dB"], "| 最終", v["final"])

wb = xlsxwriter.Workbook("out/MPI_ver4_候補8_10年窓と最大下落率.xlsx", {"use_future_functions": True})
F = dict(h=wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True, "border": 1}),
         yen=wb.add_format({"num_format": "#,##0"}), x2=wb.add_format({"num_format": "0.00"}), x3=wb.add_format({"num_format": "0.000"}),
         pct=wb.add_format({"num_format": "0.0%"}), b=wb.add_format({"bold": True}), t=wb.add_format({"bold": True, "font_size": 14}),
         sci=wb.add_format({"num_format": "0.00E+00"}), d=wb.add_format({"num_format": "yyyy-mm-dd"}),
         wrap=wb.add_format({"text_wrap": True, "valign": "top"}), big=wb.add_format({"bold": True, "font_size": 12, "bg_color": "#FFF2CC"}))
FM = {"F": F["yen"], "D": F["pct"], "MAR": F["x3"]}
ws0 = wb.add_worksheet("判定"); wsd = wb.add_worksheet("検証設計"); wsk = wb.add_worksheet("記述")
VERIFY = {}                                    # verify スクリプト用のセル位置と期待値


# ------------------------------------------------------------------ データ + 窓の値（数式）
def data_and_windows(tag, df, W, vlist, lump=True, extra=False):
    """データシート（締め日ごと）と、窓の値シート（MEDIAN(IF) で締め日21通りの中央値）を書く。
    extra=True なら A・B の 月末締めだけ(k=0)MAR と ドル建て D・MAR も数式で"""
    wd = wb.add_worksheet(f"データ_{tag}"); ww = wb.add_worksheet(f"窓_{tag}"); wp = wb.add_worksheet(f"窓_{tag}_Py")
    cols = ["セット", "開始", "案", "締め日k", "年数", "税引後最終資産F(円)", "年率R(数式)" if lump else "年率R=IRR(Python)",
            "最大下落率D", "MAR=R÷|D|(数式)", "D ドル建て", "MAR ドル建て(数式)", "キー(数式)"]
    for j, c in enumerate(cols): wd.write(0, j, c, F["h"])
    for j, s in enumerate(SETORDER): wd.write(j, 14, s)
    for j, v in enumerate(ALLV): wd.write(j, 15, v)
    df = df[df["var"].isin(vlist)].reset_index(drop=True)
    N = len(df) + 1
    key = lambda s, st, v, sh="": f"MATCH({s},{sh}$O$1:$O${len(SETORDER)},0)*1000000+VALUE(LEFT({st},4))*100+MATCH({v},{sh}$P$1:$P${len(ALLV)},0)"
    for i, x in enumerate(df.itertuples(), start=1):
        r_ = i + 1
        wd.write(i, 0, x.set); wd.write(i, 1, x.start); wd.write(i, 2, x.var); wd.write_number(i, 3, x.k); wd.write_number(i, 4, x.years)
        wd.write_number(i, 5, x.final, F["yen"])
        if lump: wd.write_formula(i, 6, f"=(F{r_}/{INITIAL!r})^(1/E{r_})-1", F["pct"])
        else: wd.write_number(i, 6, x.R, F["pct"])
        wd.write_number(i, 7, x.D, F["pct"]); wd.write_formula(i, 8, f"=G{r_}/ABS(H{r_})", F["x3"])
        wd.write_number(i, 9, x.mdd_usd, F["pct"]); wd.write_formula(i, 10, f"=G{r_}/ABS(J{r_})", F["x3"])
        wd.write_formula(i, 11, "=" + key(f"A{r_}", f"B{r_}", f"C{r_}"))
    wd.freeze_panes(1, 4)
    Dc = lambda c: f"データ_{tag}!${c}$2:${c}${N}"
    DCOL = {"F": "F", "D": "H", "MAR": "I", "Du": "J", "MARu": "K"}
    wins = W.reset_index()[["set", "start", "end"]].drop_duplicates().reset_index(drop=True)
    NW = len(wins) + 1
    hdr = ["セット", "開始", "終了"]; spec = []
    for v in vlist:
        for m, _ in MET:
            hdr.append(f"{m}_{v}"); spec.append((v, m, "med"))
    if extra:
        for v in ("A", "B"):
            for m in ("MAR", "D"):
                hdr.append(f"{m}月末締め_{v}"); spec.append((v, m, "k0"))
        for v in ("A", "B"):
            for m in ("Du", "MARu"):
                hdr.append(f"{m}_{v}"); spec.append((v, m, "med"))
    C0 = 3; col = {h: CN(C0 + j) for j, h in enumerate(hdr[3:])}
    flags = [("勝ち_F", "F"), ("勝ち_D", "D"), ("勝ち_MAR", "MAR")]
    for j, h in enumerate(hdr + [f for f, _ in flags]):
        ww.write(0, j, h, F["h"]); wp.write(0, j, h, F["h"]) if j < len(hdr) else None
    pyc = {"F": "final", "D": "D", "MAR": "MAR", "Du": "mdd_usd", "MARu": "MARu"}
    for i, x in enumerate(wins.itertuples(), start=1):
        r_ = i + 1
        for w_ in (ww, wp): w_.write(i, 0, x.set); w_.write(i, 1, x.start); w_.write(i, 2, x.end)
        for j, (v, m, how) in enumerate(spec):
            kf = key(f"$A{r_}", f"$B{r_}", f'"{v}"', f"データ_{tag}!"); fm = FM.get(m.replace("u", ""), F["x3"])
            if how == "med":
                ww.write_array_formula(i, C0 + j, i, C0 + j, f"{{=MEDIAN(IF({Dc('L')}={kf},{Dc(DCOL[m])}))}}", fm)
                wp.write_number(i, C0 + j, float(W.loc[(x.set, x.start, x.end, v), pyc[m]]), fm)
            else:
                ww.write_formula(i, C0 + j, f"=SUMIFS({Dc(DCOL[m])},{Dc('L')},{kf},{Dc('D')},0)", fm)
                wp.write_number(i, C0 + j, float(WK0.loc[(x.set, x.start, x.end, v), pyc[m]]), fm)
        for j, (fn, m) in enumerate(flags):
            a, b = f"{col[m + '_A']}{r_}", f"{col[m + '_B']}{r_}"
            ww.write_formula(i, C0 + len(spec) + j, f'=IF(ABS({a}-{b})<={TIE!r}*ABS({b}),"同じ",IF({a}>{b},"A","B"))')
            col[fn] = CN(C0 + len(spec) + j)
    last = CN(C0 + len(spec) - 1)
    ww.write(0, C0 + len(spec) + 4, "Pythonとの最大|乖離率|", F["b"])
    ww.write_array_formula(0, C0 + len(spec) + 5, 0, C0 + len(spec) + 5,
                           f"{{=MAX(ABS(D2:{last}{NW}/'窓_{tag}_Py'!D2:{last}{NW}-1))}}", F["sci"])
    VERIFY[f"窓_{tag}"] = (1, C0 + len(spec) + 6)
    ww.freeze_panes(1, 3); ww.set_column(0, 0, 22)
    rng = lambda h: f"'窓_{tag}'!${col[h]}$2:${col[h]}${NW}"
    return dict(rng=rng, setr=f"'窓_{tag}'!$A$2:$A${NW}", col=col, wins=wins)


SH10 = data_and_windows("10年", R[R.wtype == "10年窓"], W10, ALLV, extra=True)
SH5 = data_and_windows("5年", R[R.wtype == "5年窓"], W5, ["A", "B"])
SHM = data_and_windows("月3万", R[R.wtype == "10年窓+月3万"], WM, ["A", "B"], lump=False)

# ------------------------------------------------------------------ 判定ブロック（数式）
CHK = []        # (sheet, row0, col0, 期待値, 'abs'|'rel')


def decision_block(ws, r, title, sh, mA, mB, dA, dB, dec, sname):
    ws.write(r, 0, title, F["b"]); r += 1
    for j, c in enumerate(["セット", "区分", "窓の数", "MAR中央値 A", "MAR中央値 B", "MARが上", "最大下落率の中央値 A", "最大下落率の中央値 B", "下落が浅い"]):
        ws.write(r, j, c, F["h"])
    r += 1; r1 = r + 1
    med = lambda h, s: f"MEDIAN(IF({sh['setr']}={s},{sh['rng'](h)}))"
    for s in SETORDER:
        e = r + 1
        ws.write(r, 0, s); ws.write(r, 1, KIND[s]); ws.write_formula(r, 2, f"=COUNTIF({sh['setr']},$A{e})")
        for j, (h, fm, c_, k_) in enumerate([(mA, F["x3"], "A", 0), (mB, F["x3"], "B", 0)]):
            ws.write_array_formula(r, 3 + j, r, 3 + j, "{=" + med(h, f"$A{e}") + "}", fm)
        ws.write_formula(r, 5, f'=IF(D{e}>E{e},"A",IF(E{e}>D{e},"B","同じ"))')
        for j, h in enumerate([dA, dB]):
            ws.write_array_formula(r, 6 + j, r, 6 + j, "{=" + med(h, f"$A{e}") + "}", F["pct"])
        ws.write_formula(r, 8, f'=IF(G{e}>H{e},"A",IF(H{e}>G{e},"B","同じ"))')
        mcol, dcol = ("MARu", "mdd_usd") if mA.startswith("MARu") else ("MAR", "D")
        for c_, v_, cc in [(3, "A", mcol), (4, "B", mcol), (6, "A", dcol), (7, "B", dcol)]:
            CHK.append((sname, r, c_, float(dec["sv"].loc[(s, v_), cc]), "rel"))
        r += 1
    r2 = r
    rows = [("ISでMARが上の案", f"=F{r1}", dec["up"][IS]),
            ("OOS 5セットのうち A が上の数", f'=COUNTIF(F{r1 + 1}:F{r2},"A")', dec["nA"]),
            ("OOS 5セットのうち B が上の数", f'=COUNTIF(F{r1 + 1}:F{r2},"B")', dec["nB"]),
            ("主判定（IS かつ OOS 5中3以上）", f'=IF(AND(F{r1}="A",B{r + 2}>=3),"A",IF(AND(F{r1}="B",B{r + 3}>=3),"B","優劣なし"))', dec["main"]),
            ("下落が浅いセットの数 A（6セット中）", f'=COUNTIF(I{r1}:I{r2},"A")', dec["dA"]),
            ("下落が浅いセットの数 B（6セット中）", f'=COUNTIF(I{r1}:I{r2},"B")', dec["dB"]),
            ("採用（主判定→下落の浅さ→据え置きA）", f'=IF(B{r + 4}<>"優劣なし",B{r + 4},IF(B{r + 5}>B{r + 6},"A",IF(B{r + 6}>B{r + 5},"B","A(据え置き)")))', dec["final"])]
    out = {}
    for lab, fml, py in rows:
        ws.write(r, 0, lab, F["b"]); ws.write_formula(r, 1, fml, F["big"] if lab.startswith(("主判定", "採用")) else None)
        ws.write(r, 2, "Python:"); ws.write(r, 3, py)
        out[lab] = (r + 1, 2, py); r += 1
    VERIFY.setdefault("text", []).extend((sname, rr, cc, py, lab + "｜" + title) for lab, (rr, cc, py) in out.items())
    for i, s in enumerate(SETORDER):
        VERIFY["text"].append((sname, r1 + i, 6, dec["up"][s], f"MARが上 {s}｜{title}"))
        VERIFY["text"].append((sname, r1 + i, 9, dec["sh"][s], f"下落が浅い {s}｜{title}"))
    return r + 1


def chk_cell(ws, r, c, sname, label):
    items = [x for x in CHK if x[0] == sname]; parts = []
    for i in range(0, len(items), 150):
        t = [(f"ABS({CN(c_)}{r_ + 1}/{v!r}-1)" if k_ == "rel" else f"ABS({CN(c_)}{r_ + 1}-{v!r})") for _, r_, c_, v, k_ in items[i:i + 150]]
        parts.append("MAX(" + ",".join(t) + ")")
    ws.write(r, c, label, F["b"]); VERIFY.setdefault("chk", []).append((sname, r + 1, c + 2, label))
    if len(parts) == 1: ws.write_formula(r, c + 1, "=" + parts[0], F["sci"])
    else:
        for i, p_ in enumerate(parts): ws.write_formula(r, c + 2 + i, "=" + p_, F["sci"])
        ws.write_formula(r, c + 1, f"=MAX({CN(c + 2)}{r + 1}:{CN(c + 1 + len(parts))}{r + 1})", F["sci"])


ws = ws0; ws.set_column(0, 0, 40); ws.set_column(1, 8, 15)
ws.write(0, 0, "候補8: A 米ドルMMF・6%超→2倍 と B 全額すぐ1倍・3倍固定 を、10年窓と最大下落率で比べる（100万円一括）", F["t"])
ws.write(1, 0, "現実コストC・税引後・円建て。窓の値＝締め日21通りの中央値、セットの値＝窓の値の中央値。すべて数式（データ_10年 → 窓_10年 → この表）")
r = decision_block(ws, 3, "【主判定】10年窓・円建ての最大下落率・締め日21通りの中央値", SH10, "MAR_A", "MAR_B", "D_A", "D_B", DEC["main"], "判定")
MAINROW = r
r = decision_block(ws, r + 1, "【感応度1】月末締めだけ（k=0）", SH10, "MAR月末締め_A", "MAR月末締め_B", "D月末締め_A", "D月末締め_B", DEC["k0"], "判定")
r = decision_block(ws, r + 1, "【感応度2】ドル建ての最大下落率", SH10, "MARu_A", "MARu_B", "Du_A", "Du_B", DEC["usd"], "判定")
r = decision_block(ws, r + 1, "【感応度3】5年窓", SH5, "MAR_A", "MAR_B", "D_A", "D_B", DEC["y5"], "判定")
r = decision_block(ws, r + 1, "【感応度4】100万円＋月3万円（10年窓。年率＝IRR、最大下落率＝時間加重・ドル建て）", SHM, "MAR_A", "MAR_B", "D_A", "D_B", DEC["m3"], "判定")
chk_cell(ws, r + 1, 0, "判定", "Pythonとの最大|乖離率|（この表の中央値）")
ws.freeze_panes(3, 1)

# ------------------------------------------------------------------ 記述（判定に使わない）
ws = wsk; ws.set_column(0, 0, 24); ws.set_column(1, 30, 13)
ws.write(0, 0, "記述統計（判定に使わない）。10年窓・窓の値から数式で集計", F["t"])
THR = [-0.5, -0.6, -0.7, -0.8, -0.9]
r = 2
hd = ["セット", "窓の数", "Fの中央値 A(円)", "Fの中央値 B(円)", "F勝ち A", "F勝ち B", "F同じ", "D勝ち(浅い) A", "D勝ち B", "D同じ", "MAR勝ち A", "MAR勝ち B", "MAR同じ",
      "元本割れの窓 A", "元本割れの窓 B", "最悪の窓のF A(円)", "最悪の窓のF B(円)", "最悪の窓のD A", "最悪の窓のD B"]
hd += [f"Dが{int(t * 100)}%より深い窓の割合 {v}" for t in THR for v in ("A", "B")]
for j, c in enumerate(hd): ws.write(r, j, c, F["h"])
ws.set_row(r, 60); r += 1
W10r = W10.reset_index()
P = {v: W10r[W10r["var"] == v].set_index(["set", "start"]) for v in ALLV}
DESC = {}
S_, G_ = SH10["setr"], SH10["rng"]
for s in SETORDER:
    e = r + 1; a, b = P["A"].loc[s], P["B"].loc[s]
    ws.write(r, 0, s); ws.write_formula(r, 1, f"=COUNTIF({S_},$A{e})"); CHK.append(("記述", r, 1, float(len(a)), "abs"))
    c = 2
    for v, x in (("A", a), ("B", b)):
        ws.write_array_formula(r, c, r, c, f"{{=MEDIAN(IF({S_}=$A{e},{G_('F_' + v)}))}}", F["yen"]); CHK.append(("記述", r, c, float(x.final.median()), "rel")); c += 1
    for m, pc in (("F", "final"), ("D", "D"), ("MAR", "MAR")):
        tie = np.isclose(a[pc], b[pc], rtol=TIE, atol=0.0)      # 浮動小数の誤差(1e-16程度)だけの差は「同じ」
        for lab, cnt in (("A", int(((a[pc] > b[pc]) & ~tie).sum())), ("B", int(((b[pc] > a[pc]) & ~tie).sum())), ("同じ", int(tie.sum()))):
            ws.write_formula(r, c, f'=COUNTIFS({S_},$A{e},{G_("勝ち_" + m)},"{lab}")'); CHK.append(("記述", r, c, float(cnt), "abs")); c += 1
    for v, x in (("A", a), ("B", b)):
        ws.write_formula(r, c, f'=COUNTIFS({S_},$A{e},{G_("F_" + v)},"<"&{INITIAL!r})'); CHK.append(("記述", r, c, float((x.final < INITIAL).sum()), "abs")); c += 1
    for m, pc, fm in (("F", "final", F["yen"]), ("D", "D", F["pct"])):
        for v, x in (("A", a), ("B", b)):
            ws.write_array_formula(r, c, r, c, f"{{=MIN(IF({S_}=$A{e},{G_(m + '_' + v)}))}}", fm); CHK.append(("記述", r, c, float(x[pc].min()), "rel")); c += 1
    for t in THR:
        for v, x in (("A", a), ("B", b)):
            ws.write_formula(r, c, f'=COUNTIFS({S_},$A{e},{G_("D_" + v)},"<"&{t!r})/$B{e}', F["pct"]); CHK.append(("記述", r, c, float((x.D < t).mean()), "abs")); c += 1
    DESC[s] = dict(n=len(a), a=a, b=b)
    r += 1
r += 1
ws.write(r, 0, "参考の案も含めた中央値（10年窓、数式）", F["b"]); r += 1
for m, pc, fm in (("MAR", "MAR", F["x3"]), ("F", "final", F["yen"]), ("D", "D", F["pct"])):
    ws.write(r, 0, {"MAR": "MAR中央値", "F": "Fの中央値(円)", "D": "最大下落率の中央値"}[m], F["h"])
    for j, v in enumerate(ALLV): ws.write(r, 1 + j, VARN[v], F["h"])
    ws.set_row(r, 45); r += 1
    for s in SETORDER:
        ws.write(r, 0, s)
        for j, v in enumerate(ALLV):
            ws.write_array_formula(r, 1 + j, r, 1 + j, f"{{=MEDIAN(IF({S_}=$A{r + 1},{G_(m + '_' + v)}))}}", fm)
            CHK.append(("記述", r, 1 + j, float(P[v].loc[s][pc].median()), "rel"))
        r += 1
    r += 1
# 参考: NDX 2022/9-2026（全期間、締め日21通りの中央値）
REF = R[R.wtype == "参考全期間"].reset_index(drop=True)
ws.write(r, 0, f"参考: {REFSET[0]}（全期間。10年窓が取れないので判定に数えない）", F["b"]); r += 1
for j, c in enumerate(["案", "F 中央値(円, 数式)", "年率R(数式)", "最大下落率D 中央値(数式)", "MAR(数式)"]): ws.write(r, j, c, F["h"])
r += 1; r0 = r + 40
for j, c in enumerate(["案", "締め日k", "F(円)", "D", "年数"]): ws.write(r0 - 1, 10 + j, c, F["h"])
for i, x in enumerate(REF.itertuples()):
    ws.write(r0 + i, 10, x.var); ws.write_number(r0 + i, 11, x.k); ws.write_number(r0 + i, 12, x.final, F["yen"]); ws.write_number(r0 + i, 13, x.D, F["pct"])
    ws.write_number(r0 + i, 14, x.years)
rv = f"$K${r0 + 1}:$K${r0 + len(REF)}"
REFM = REF.groupby("var")[["final", "D", "MAR", "R"]].median()
for v in ALLV:
    e = r + 1; ws.write(r, 0, v); ws.write(r, 5, VARN[v])
    ws.write_array_formula(r, 1, r, 1, f"{{=MEDIAN(IF({rv}=$A{e},$M${r0 + 1}:$M${r0 + len(REF)}))}}", F["yen"])
    ws.write_formula(r, 2, f"=(B{e}/{INITIAL!r})^(1/$O${r0 + 1})-1", F["pct"])
    ws.write_array_formula(r, 3, r, 3, f"{{=MEDIAN(IF({rv}=$A{e},$N${r0 + 1}:$N${r0 + len(REF)}))}}", F["pct"])
    ws.write_array_formula(r, 4, r, 4, f"{{=MEDIAN(IF({rv}=$A{e},((($M${r0 + 1}:$M${r0 + len(REF)})/{INITIAL!r})^(1/$O${r0 + 1})-1)/ABS($N${r0 + 1}:$N${r0 + len(REF)})))}}", F["x3"])
    for c_, pc in ((1, "final"), (2, "R"), (3, "D"), (4, "MAR")): CHK.append(("記述", r, c_, float(REFM.loc[v, pc]), "rel"))
    r += 1
chk_cell(ws, 1, 0, "記述", "Pythonとの最大|差|（この表）")

rows_ = [("項目", "内容"),
         ("事前登録", "candidate8_prereg.md（計算前にコミット 32fdcb3）。結果を見てから指標・窓・閾値を変えていない"),
         ("比べる2案", "A = 米ドルMMF・6%超→2倍 / B = 全額すぐ1倍・3倍固定。どちらも12か月線・100万円一括・積立なし"),
         ("窓", "10年窓（毎年1月開始）。IS = NDX 1989-2026、OOS 5セット。NDX 2022/9-2026 は参考（記述シート）"),
         ("指標", "F=税引後最終資産 / R=税引後年率=(F÷100万)^(1/10)−1 / D=最大下落率（円建て日次評価額）/ MAR=R÷|D|"),
         ("集計", "窓の値=締め日21通りの中央値（MARは締め日ごとに計算してから中央値）。セットの値=窓の値の中央値"),
         ("主判定", "MAR中央値で IS かつ OOS 5セット中3以上で上回った案を採用。優劣なしなら最大下落率の中央値が浅いセット数→同数ならA据え置き"),
         ("感応度", "月末締めだけ / ドル建ての最大下落率 / 5年窓 / 100万円+月3万円。判定には使わない"),
         ("限界", "窓は重なっていて独立ではない（勝ち数は記述統計）。NASDAQ総合1974-85は2窓だけ。MMFの為替差損益は非課税扱い、経費率0.3%は仮定")]
wsd.set_column(0, 0, 14); wsd.set_column(1, 1, 130)
for i, rr_ in enumerate(rows_):
    for j, x in enumerate(rr_): wsd.write(i, j, x, F["h"] if i == 0 else F["wrap"])

# ------------------------------------------------------------------ 数式検算: 12か月線シグナル（日次生データから）+ A / B の日次台帳（NDX 2000-2009、最大下落率まで）
DN = pd.read_pickle("data/daily_NDX.pkl"); ND = len(DN) + 1
sig12 = O["sig0"]["NDX"]; NB = len(sig12)
SN = "検算_12か月線"; ws = wb.add_worksheet(SN)
for j, c in enumerate(["日付", "終値", "月末(数式)", "月末累計(数式)", "足番号(数式)"]): ws.write(0, j, c, F["h"])
for i, (dt_, x) in enumerate(DN.iterrows()):
    r_ = i + 2
    ws.write_datetime(i + 1, 0, dt_.to_pydatetime(), F["d"]); ws.write_number(i + 1, 1, x.c)
    ws.write_formula(i + 1, 2, f"=IF(MONTH(A{r_ + 1})<>MONTH(A{r_}),1,0)" if i < len(DN) - 1 else "=1")
    ws.write_formula(i + 1, 3, f"=C{r_}" if i == 0 else f"=D{r_ - 1}+C{r_}")
    ws.write_formula(i + 1, 4, "=0" if i == 0 else f"=D{r_ - 1}")
for j, c in enumerate(["足#", "終値(数式)", "12か月平均", "状態", "前の状態", "シグナル(数式)", "シグナル(Py)", "一致"]): ws.write(0, 6 + j, c, F["h"])
Gr = f"$E$2:$E${ND}"
for j in range(NB):
    r_ = j + 2; p = r_ - 1
    ws.write_number(j + 1, 6, j)
    ws.write_formula(j + 1, 7, f'=INDEX($B$2:$B${ND},COUNTIF({Gr},"<="&G{r_}))')
    if j >= 11:
        ws.write_formula(j + 1, 8, f"=AVERAGE(H{r_ - 11}:H{r_})"); ws.write_formula(j + 1, 9, f"=IF(H{r_}>I{r_},1,0)")
    else:
        ws.write(j + 1, 9, "")
    ws.write_formula(j + 1, 10, "=0" if j == 0 else f'=IF(J{p}="",K{p},J{p})')
    ws.write_formula(j + 1, 11, f'=IF(J{r_}="",0,IF(J{r_}<>K{r_},IF(J{r_}=1,1,-1),0))')
    ws.write_number(j + 1, 12, int(sig12.sig.iloc[j])); ws.write_formula(j + 1, 13, f"=IF(L{r_}=M{r_},1,0)")
NBr = NB + 1
ws.write(1, 15, "シグナル不一致数(数式)", F["b"]); ws.write_formula(1, 16, f"=COUNT(G2:G{NBr})-SUM(N2:N{NBr})")
c3, c2 = COST["NDX"]
LS, LE = "2000-01", "2009-12"
dd = DN.loc[LS + "-01": "2009-12-31"]; off = DN.index.get_loc(dd.index[0])
LED = {}
for v in ("A", "B"):
    kw = VARS[v]; mode_ = kw["exit_mode"]; thr = kw.get("rate_thr")
    cfgL = Cfg(name="ledger", lev_cost=c3, lev_cost_lo=c2, financing=True, one_er=0.0015, dividends=True, exec_lag=1, contrib_at_month_end=False,
               tax_on=False, infl_adj=False, start=LS, end=LE, initial=INITIAL, monthly=0.0, **kw)
    rL, hL = run_rule(DN, sig12, cfgL)
    assert len(hL) == len(dd)
    nm = f"検算_台帳_{v}"; ws = wb.add_worksheet(nm)
    LC = ["日付", "r", "暦日数", "米3M金利", "1倍配当(日)", "3倍日次", "2倍日次", "1倍日次", "月初", "約定シグナル", "前営業日の金利", "持つべき倍率",
          "レバ枠 成長後", "1倍 成長後", "現金(MMF) 成長後", "売実行", "買実行", "状態", "保有倍率(期末)", "投入額",
          "レバ枠 期末", "1倍 期末", "現金 期末", "総資産(数式)", "総資産(Python)", "乖離率", "それまでの最高値", "下落率"]
    for j, c in enumerate(LC): ws.write(0, j, c, F["h"])
    prm = [("c3（3倍の総合コスト）", c3), ("c2（2倍の総合コスト）", c2), ("1倍経費率", 0.0015), ("MMF手数料", 0.003), ("初期投資", INITIAL),
           ("置き場", mode_), ("金利ルールの閾値（なし=99）", thr if thr is not None else 99.0)]
    for i, (t, x) in enumerate(prm):
        ws.write(i, 29, t); (ws.write_number if isinstance(x, float) else ws.write)(i, 30, x)
    ws.write(7, 29, "開始時の状態(数式)"); ws.write_formula(7, 30, f"=INDEX({SN}!$K$2:$K${NBr},{SN}!E{off + 2}+1)")
    ws.write(8, 29, "開始時の状態(Py: long=1)"); ws.write_number(8, 30, 1 if init_regime(sig12, LS) == "long" else 0)
    for i, (dt_, x) in enumerate(dd.iterrows()):
        r_ = i + 2; p = r_ - 1; sr = off + 2 + i; z = i == 0
        pv = (lambda c: "0") if z else (lambda c: f"{c}{p}")
        reg = "$AE$8" if z else f"R{p}"
        ws.write_formula(i + 1, 0, f"={SN}!A{sr}", F["d"])
        ws.write_formula(i + 1, 1, f"={SN}!B{sr}/{SN}!B{sr - 1}-1")
        ws.write_number(i + 1, 2, x["dt"]); ws.write_number(i + 1, 3, x["rf"]); ws.write_number(i + 1, 4, x["dy"])
        ws.write_formula(i + 1, 5, f"=3*(B{r_}+E{r_})-2*D{r_}*C{r_}/365-$AE$1*C{r_}/365")
        ws.write_formula(i + 1, 6, f"=2*(B{r_}+E{r_})-1*D{r_}*C{r_}/365-$AE$2*C{r_}/365")
        ws.write_formula(i + 1, 7, f"=B{r_}-$AE$3*C{r_}/365")
        ws.write_formula(i + 1, 8, "=1" if z else f"=IF(MONTH(A{r_})<>MONTH(A{p}),1,0)")
        ws.write_formula(i + 1, 9, "=0" if z else f"=IF({SN}!E{sr}<>{SN}!E{sr - 1},INDEX({SN}!$L$2:$L${NBr},{SN}!E{sr - 1}+1),0)")
        ws.write_formula(i + 1, 10, f"=D{r_}" if z else f"=D{p}")
        ws.write_formula(i + 1, 11, f"=IF(K{r_}>$AE$7,2,3)")
        ws.write_formula(i + 1, 12, "=0" if z else f"=U{p}*(1+IF(S{p}=2,G{r_},F{r_}))")
        ws.write_formula(i + 1, 13, "=0" if z else f"=V{p}*(1+H{r_})*(1+E{r_})")
        ws.write_formula(i + 1, 14, "=0" if z else f'=IF($AE$6="mmf",W{p}*(1+MAX(D{r_}-$AE$4,0)*C{r_}/365),W{p})')
        ws.write_formula(i + 1, 15, f"=AND(J{r_}=-1,{reg}=1)"); ws.write_formula(i + 1, 16, f"=AND(J{r_}=1,{reg}=0)")
        ws.write_formula(i + 1, 17, f"=IF(P{r_},0,IF(Q{r_},1,{reg}))")
        ws.write_formula(i + 1, 18, f"=IF(R{r_}=1,L{r_},3)" if z else f"=IF(R{r_}=1,IF(OR(Q{r_},I{r_}=1),L{r_},S{p}),S{p})")
        ws.write_formula(i + 1, 19, "=$AE$5" if z else "=0")
        ws.write_formula(i + 1, 20, f"=IF(P{r_},0,IF(Q{r_},M{r_}+N{r_}+O{r_},M{r_}))+IF(R{r_}=1,T{r_},0)")
        ws.write_formula(i + 1, 21, f'=IF(Q{r_},0,N{r_})+IF(AND(P{r_},$AE$6="one"),O{r_}+M{r_},0)+IF(AND(R{r_}=0,$AE$6="one"),T{r_},0)')
        ws.write_formula(i + 1, 22, f'=IF(P{r_},IF($AE$6="one",0,O{r_}+M{r_}),IF(Q{r_},0,O{r_}))+IF(AND(R{r_}=0,$AE$6="mmf"),T{r_},0)')
        ws.write_formula(i + 1, 23, f"=U{r_}+V{r_}+W{r_}", F["yen"])
        ws.write_number(i + 1, 24, hL.value_ccy.iloc[i], F["yen"])
        ws.write_formula(i + 1, 25, f"=X{r_}/Y{r_}-1", F["sci"])
        ws.write_formula(i + 1, 26, f"=X{r_}" if z else f"=MAX(AA{p},X{r_})", F["yen"])
        ws.write_formula(i + 1, 27, f"=X{r_}/AA{r_}-1", F["pct"])
    NL = len(dd) + 1
    ws.write(10, 29, "最大|乖離率|", F["b"]); ws.write_array_formula(10, 30, 10, 30, f"{{=MAX(ABS(Z2:Z{NL}))}}", F["sci"])
    ws.write(11, 29, "最終(数式)"); ws.write_formula(11, 30, f"=X{NL}", F["yen"])
    ws.write(12, 29, "最終(Python)"); ws.write_number(12, 30, rL["final_pre_liq"], F["yen"])
    ws.write(13, 29, "最大下落率(数式)"); ws.write_formula(13, 30, f"=MIN(AB2:AB{NL})", F["pct"])
    ws.write(14, 29, "最大下落率(Python)"); ws.write_number(14, 30, rL["mdd_value"], F["pct"])
    ws.write(15, 29, "最大下落率の差", F["b"]); ws.write_formula(15, 30, "=AE14-AE15", F["sci"])
    ws.write(16, 29, "2倍を持った日数(数式)"); ws.write_formula(16, 30, f'=COUNTIFS(R2:R{NL},1,S2:S{NL},2)')
    ws.write(17, 29, "2倍を持った日数(Python)"); ws.write_number(17, 30, int((hL.regime == "long2").sum()))
    ws.set_column(29, 29, 28); ws.freeze_panes(1, 1)
    LED[v] = nm
    print(v, "台帳 最終", round(rL["final_pre_liq"]), "最大下落率", round(rL["mdd_value"], 4), "2倍日数", int((hL.regime == "long2").sum()))
wb.close()
pd.to_pickle(dict(VERIFY=VERIFY, LED=LED, DEC={k_: {x: v[x] for x in ("up", "sh", "nA", "nB", "main", "dA", "dB", "final")} for k_, v in DEC.items()},
                  MAINROW=MAINROW), "data/candidate8_report.pkl")
print("excel ok", len(CHK))
