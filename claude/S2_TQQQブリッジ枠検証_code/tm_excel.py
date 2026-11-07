"""総合マニュアルのExcel突合（2026-11-07）：入力（各口座の日次の価値・株フラグ・MCの経路）から数式で再計算し、Pythonと照合"""
import sys, json, datetime as dt
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter as L

OUT = "out_tm"
D = pd.read_csv(f"{OUT}/daily.csv", index_col=0, parse_dates=True)
I = pd.read_csv(f"{OUT}/indicators.csv", index_col=0)
Y = pd.read_csv(f"{OUT}/yearly.csv", index_col=0)
RE = pd.read_csv(f"{OUT}/rules_eval.csv")
RD = pd.read_csv(f"{OUT}/rules_daily.csv", index_col=0, parse_dates=True)
MC = pd.read_csv(f"{OUT}/mc.csv").set_index("期間")
MA = pd.read_csv(f"{OUT}/mc_accounts.csv")
P = pd.read_csv(f"{OUT}/mc_paths.csv")
meta = json.load(open(f"{OUT}/meta.json"))
b = Font(bold=True)
xl_date = lambda s: (pd.Timestamp(s) - pd.Timestamp("1899-12-30")).days
checks = []          # (項目, シート, セル, Python値, 許容差)

wb = Workbook()
# ---------------- 条件 ----------------
wc = wb.active; wc.title = "条件"
wc["A1"] = "世帯＝今の構成比（11/6実額）を毎月末に保つ。比率はS2・DC・NISAの実額から計算"; wc["A1"].font = b
for k, (lab, v) in enumerate([("S2 口座（円）", meta["W0"]), ("DC（円）", meta["D0"]), ("NISA（円）", meta["N0"])]):
    wc.cell(3 + k, 1, lab); wc.cell(3 + k, 2, float(v)); wc.cell(3 + k, 3, f"=B{3+k}/SUM($B$3:$B$5)")
wc["C2"] = "比率(式)"
W1, W2, W3 = "条件!$C$3", "条件!$C$4", "条件!$C$5"

# ---------------- 日次 ----------------
wd = wb.create_sheet("日次")
n = len(D); R0, Rl = 3, 3 + n - 1
INP = ["S2", "S2換金後", "DC", "NISA", "QQQ", "株_S2", "株_DC", "世帯", "世帯換金後"]     # B..J（世帯2本はPythonの値、照合用）
for j, c in enumerate(INP):
    wd.cell(1, 2 + j, c + ("(Python)" if c.startswith("世帯") else "(入力)")).font = b
# 世帯の再計算：K..P
HC = {"aS2": 11, "aS2L": 12, "aDC": 13, "aN": 14, "aH": 15, "aHL": 16, "H": 17, "HL": 18}
for k, v in HC.items():
    wd.cell(1, v, {"aS2": "月初の基準 S2", "aS2L": "月初の基準 S2換金後", "aDC": "月初の基準 DC", "aN": "月初の基準 NISA",
                   "aH": "月初の基準 世帯", "aHL": "月初の基準 世帯換金後", "H": "世帯(式)", "HL": "世帯換金後(式)"}[k]).font = b
SER = {"世帯": L(HC["H"]), "世帯換金後": L(HC["HL"]), "S2": "B", "S2換金後": "C", "DC": "D", "NISA": "E", "QQQ": "F"}
SN = list(SER)
SUB = ["日次リターン", "下落日", "高値", "高値からの下落", "高値の日"]
C0 = 19
def cols(s):
    j = SN.index(s); c = C0 + j * 5
    return SER[s], L(c), L(c + 1), L(c + 2), L(c + 3), L(c + 4)
for s in SN:
    N, RT, NG, RM, DD, PD = cols(s)
    for t, h in enumerate(SUB):
        wd.cell(1, C0 + SN.index(s) * 5 + t, f"{s} {h}(式)").font = b
B_, C_, D_, E_ = "B", "C", "D", "E"
aS2, aS2L, aDC, aN, aH, aHL, H, HL = (L(HC[k]) for k in ["aS2", "aS2L", "aDC", "aN", "aH", "aHL", "H", "HL"])
for r, d in enumerate(D.index):
    R = R0 + r
    wd.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    for j, c in enumerate(INP):
        wd.cell(R, 2 + j, float(D[c].iloc[r]))
    if r == 0:
        for a, src in [(aS2, B_), (aS2L, C_), (aDC, D_), (aN, E_)]:
            wd[f"{a}{R}"] = f"={src}{R}"
        wd[f"{aH}{R}"] = 1; wd[f"{aHL}{R}"] = 1
    else:
        chg = f"MONTH(A{R})<>MONTH(A{R-1})"
        for a, src in [(aS2, B_), (aS2L, C_), (aDC, D_), (aN, E_)]:
            wd[f"{a}{R}"] = f"=IF({chg},{src}{R-1},{a}{R-1})"
        wd[f"{aH}{R}"] = f"=IF({chg},{H}{R-1},{aH}{R-1})"
        wd[f"{aHL}{R}"] = f"=IF({chg},{HL}{R-1},{aHL}{R-1})"
    wd[f"{H}{R}"] = f"={aH}{R}*({W1}*B{R}/{aS2}{R}+{W2}*D{R}/{aDC}{R}+{W3}*E{R}/{aN}{R})"
    wd[f"{HL}{R}"] = f"={aHL}{R}*({W1}*C{R}/{aS2L}{R}+{W2}*D{R}/{aDC}{R}+{W3}*E{R}/{aN}{R})"
    for s in SN:
        N, RT, NG, RM, DD, PD = cols(s)
        if r > 0:
            wd[f"{RT}{R}"] = f"={N}{R}/{N}{R-1}-1"; wd[f"{NG}{R}"] = f'=IF({RT}{R}<-1E-12,{RT}{R},"")'
            wd[f"{RM}{R}"] = f"=MAX({RM}{R-1},{N}{R})"; wd[f"{PD}{R}"] = f"=IF({N}{R}>={RM}{R},A{R},{PD}{R-1})"
        else:
            wd[f"{RM}{R}"] = f"={N}{R}"; wd[f"{PD}{R}"] = f"=A{R}"
        wd[f"{DD}{R}"] = f"={N}{R}/{RM}{R}-1"
rng = lambda c: f"日次!${c}${R0}:${c}${Rl}"
wd.cell(1, 1, "日付").font = b
wd.cell(2, 1, "世帯の再計算とPythonの最大差→")
wd[f"{H}2"] = f"=SUMPRODUCT(MAX(ABS({H}{R0}:{H}{Rl}-I{R0}:I{Rl})))"
wd[f"{HL}2"] = f"=SUMPRODUCT(MAX(ABS({HL}{R0}:{HL}{Rl}-J{R0}:J{Rl})))"
checks += [("世帯（毎月末に構成比を戻す）の日次の価値：式とPythonの最大差", "日次", f"{H}2", 0.0, 1e-9),
           ("世帯換金後の日次の価値：式とPythonの最大差", "日次", f"{HL}2", 0.0, 1e-9)]

# ---------------- 月次 ----------------
me = D.resample("ME").last().index
wm = wb.create_sheet("月次")
wm.cell(1, 1, "月末").font = b
MC_ = {}
for j, s in enumerate(SN):
    c = 2 + j * 4
    MC_[s] = (L(c), L(c + 1), L(c + 2), L(c + 3))
    for t, h in enumerate(["月末の価値", "月次リターン", "5年年率", "QQQとの差"]):
        wm.cell(1, c + t, f"{s} {h}(式)").font = b
wm.cell(2, 1, "開始日")
for s in SN:
    wm[f"{MC_[s][0]}2"] = f"=日次!{SER[s]}{R0}"
for k, d in enumerate(me):
    R = 3 + k
    wm.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    for s in SN:
        cm, cr, c5, ce = MC_[s]
        wm[f"{cm}{R}"] = f"=LOOKUP(A{R},{rng('A')},{rng(SER[s])})"
        wm[f"{cr}{R}"] = f"={cm}{R}/{cm}{R-1}-1"
        if k >= 60:
            wm[f"{c5}{R}"] = f"=({cm}{R}/{cm}{R-60})^(1/5)-1"
        wm[f"{ce}{R}"] = f"={cr}{R}-{MC_['QQQ'][1]}{R}"
Rm = 3 + len(me) - 1

# ---------------- 年次 ----------------
years = list(range(2000, 2027))
wy = wb.create_sheet("年次")
wy.cell(1, 1, "年").font = b
YC = {}
for j, s in enumerate(SN):
    c = 2 + j * 4; YC[s] = (L(c), L(c + 1), L(c + 2), L(c + 3))
    for t, h in enumerate(["年末の価値(式)", "年リターン(式)", "年リターン(Python)", "差"]):
        wy.cell(1, c + t, f"{s} {h}").font = b
for k, y in enumerate(years):
    R = 2 + k; wy.cell(R, 1, y)
    for s in SN:
        cn, cr, cp, cd = YC[s]
        wy[f"{cn}{R}"] = f"=LOOKUP(DATE({y},12,31),{rng('A')},{rng(SER[s])})"
        prev = f"日次!{SER[s]}{R0}" if k == 0 else f"{cn}{R-1}"
        wy[f"{cr}{R}"] = f"={cn}{R}/{prev}-1"; wy[f"{cp}{R}"] = float(Y.loc[y, s]); wy[f"{cd}{R}"] = f"=ABS({cr}{R}-{cp}{R})"
Ry = 1 + len(years)
wy.cell(Ry + 2, 1, "最大差").font = b
for s in SN:
    cd = YC[s][3]; wy[f"{cd}{Ry+2}"] = f"=MAX({cd}2:{cd}{Ry})"
    checks.append((f"年次リターン27年の最大差：{s}", "年次", f"{cd}{Ry+2}", 0.0, 1e-12))

# ---------------- 補助（最大下落の日・回復） ----------------
wh = wb.create_sheet("補助")
for t, h in enumerate(["系列", "底の行(式)", "底の日(式)", "高値の日(式)", "高値の値(式)", "回復した日(式)"]):
    wh.cell(1, 1 + t, h).font = b
HR = {}
for k, s in enumerate(SN):
    R = 2 + k; HR[s] = R
    N, RT, NG, RM, DD, PD = cols(s)
    wh.cell(R, 1, s)
    wh[f"B{R}"] = f"=MATCH(MIN({rng(DD)}),{rng(DD)},0)"
    wh[f"C{R}"] = f"=INDEX({rng('A')},B{R})"
    wh[f"D{R}"] = f"=INDEX({rng(PD)},B{R})"
    wh[f"E{R}"] = f"=INDEX({rng(RM)},B{R})"
    wh[f"F{R}"] = f'=_xlfn.MINIFS({rng("A")},{rng(N)},">="&E{R},{rng("A")},">"&C{R})'
    for c in "CDF":
        wh[f"{c}{R}"].number_format = "yyyy-mm-dd"

# ---------------- 指標 ----------------
wi = wb.create_sheet("指標", 0)
wi.cell(1, 1, "投資指標：日次の価値から数式で再計算（世帯は毎月末に構成比を戻す式から）").font = b
hdr = ["指標"] + sum([[f"{s}(式)", f"{s}(Python)", "差"] for s in SN], [])
for j, h in enumerate(hdr, 1):
    wi.cell(3, j, h).font = b
FLAGF = {"世帯": f"({W1}*AVERAGE({rng('G')})+{W2}*AVERAGE({rng('H')})+{W3}*1)", "世帯換金後": None, "S2": f"AVERAGE({rng('G')})",
         "S2換金後": f"AVERAGE({rng('G')})", "DC": f"AVERAGE({rng('H')})", "NISA": "1", "QQQ": "1"}
FLAGF["世帯換金後"] = FLAGF["世帯"]
def fm(s, key):
    N, RT, NG, RM, DD, PD = cols(s)
    cm, cr, c5, ce = MC_[s]; qr = MC_["QQQ"][1]; cy = YC[s][1]; h = HR[s]
    yrs = f"((日次!A{Rl}-日次!A{R0})/365.25)"
    cagr = f"((日次!{N}{Rl}/日次!{N}{R0})^(1/{yrs})-1)"
    vol = f"(STDEV(日次!{RT}{R0+1}:{RT}{Rl})*SQRT(252))"
    mdd = f"MIN({rng(DD)})"
    mr = f"月次!{cr}3:{cr}{Rm}"; br = f"月次!{qr}3:{qr}{Rm}"; yr = f"年次!{cy}2:{cy}{Ry}"; ex = f"月次!{ce}3:{ce}{Rm}"
    var = f"PERCENTILE({mr},0.05)"
    return {"年率": cagr, "累積倍率": f"日次!{N}{Rl}/日次!{N}{R0}", "ボラ（年率）": vol, "最大下落": mdd,
            "最大下落の日": f"補助!C{h}", "最大下落の高値の日": f"補助!D{h}", "回復までの月数": f"(補助!F{h}-補助!D{h})/(365.25/12)",
            "回復した日": f"補助!F{h}", "シャープ": f"{cagr}/{vol}",
            "ソルティノ": f"{cagr}/(STDEV(日次!{NG}{R0+1}:{NG}{Rl})*SQRT(252))", "カルマー": f"{cagr}/ABS({mdd})",
            "最悪年": f"MIN({yr})", "最良年": f"MAX({yr})", "最悪月": f"MIN({mr})", "CVaR95（月次）": f'AVERAGEIF({mr},"<="&{var})',
            "最悪5年年率": f"MIN(月次!{c5}3:{c5}{Rm})", "勝ち月の割合": f'COUNTIF({mr},">0")/COUNT({mr})',
            "ベータ（対QQQ）": f"SLOPE({mr},{br})", "相関（対QQQ）": f"CORREL({mr},{br})",
            "上昇の追随率": f'AVERAGEIF({br},">0",{mr})/AVERAGEIF({br},">0",{br})',
            "下落の追随率": f'AVERAGEIF({br},"<0",{mr})/AVERAGEIF({br},"<0",{br})',
            "情報比（対QQQ）": f"AVERAGE({ex})*12/(STDEV({ex})*SQRT(12))", "株を持っていた割合": FLAGF[s]}[key]
DATEK = {"最大下落の日", "最大下落の高値の日", "回復した日"}
for k, key in enumerate(I.index):
    R = 4 + k; wi.cell(R, 1, key)
    for j, s in enumerate(SN):
        c = 2 + j * 3
        pv = I.loc[key, s]
        if key == "情報比（対QQQ）" and s == "QQQ":
            wi.cell(R, c, "—"); continue
        wi.cell(R, c, "=" + fm(s, key))
        v = float(xl_date(pv)) if key in DATEK else float(pv)
        wi.cell(R, c + 1, v)
        if key in DATEK:
            wi.cell(R, c).number_format = wi.cell(R, c + 1).number_format = "yyyy-mm-dd"
            wi.cell(R, c + 2, f"=ABS({L(c)}{R}-{L(c+1)}{R})"); tol = 0.0
        else:
            wi.cell(R, c + 2, f"=ABS({L(c)}{R}-{L(c+1)}{R})/MAX(1,ABS({L(c+1)}{R}))"); tol = 1e-9
        checks.append((f"指標 {key}：{s}", "指標", f"{L(c+2)}{R}", 0.0, tol))

# ---------------- ルールを外した場合（日次の価値から年率・最大下落） ----------------
wr = wb.create_sheet("ルール評価_日次")
rcols = list(RD.columns)
wr.cell(1, 1, "日付").font = b
RRl = 2 + len(RD) - 1
for j, c in enumerate(rcols):
    cc = 2 + j * 3
    wr.cell(1, cc, f"{c}(入力)").font = b; wr.cell(1, cc + 1, f"{c} 高値(式)").font = b; wr.cell(1, cc + 2, f"{c} 下落(式)").font = b
for r, d in enumerate(RD.index):
    R = 2 + r
    wr.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    for j, c in enumerate(rcols):
        cc = 2 + j * 3; N, RM, DD = L(cc), L(cc + 1), L(cc + 2)
        wr.cell(R, cc, float(RD[c].iloc[r]))
        wr[f"{RM}{R}"] = f"={N}{R}" if r == 0 else f"=MAX({RM}{R-1},{N}{R})"
        wr[f"{DD}{R}"] = f"={N}{R}/{RM}{R}-1"
we = wb.create_sheet("ルール評価")
for t, h in enumerate(["案", "系列", "年率(式)", "年率(Python)", "差", "最大下落(式)", "最大下落(Python)", "差"]):
    we.cell(1, 1 + t, h).font = b
RE_ = RE.set_index("key")
r_ = 2
for c in rcols:
    j = rcols.index(c); cc = 2 + j * 3; N, DD = L(cc), L(cc + 2)
    liq = c.endswith("_換金後"); key = c[:-4] if liq else c
    py_c = RE_.loc[key, "換金後年率" if liq else "年率"]; py_d = RE_.loc[key, "換金後最大下落" if liq else "最大下落"]
    we.cell(r_, 1, RE_.loc[key, "案"]); we.cell(r_, 2, c)
    we[f"C{r_}"] = f"=(ルール評価_日次!{N}{RRl}/ルール評価_日次!{N}2)^(365.25/(ルール評価_日次!A{RRl}-ルール評価_日次!A2))-1"
    we[f"D{r_}"] = float(py_c); we[f"E{r_}"] = f"=ABS(C{r_}-D{r_})"
    we[f"F{r_}"] = f"=MIN(ルール評価_日次!{DD}2:{DD}{RRl})"; we[f"G{r_}"] = float(py_d); we[f"H{r_}"] = f"=ABS(F{r_}-G{r_})"
    checks.append((f"ルール評価 年率：{c}", "ルール評価", f"E{r_}", 0.0, 1e-12))
    checks.append((f"ルール評価 最大下落：{c}", "ルール評価", f"H{r_}", 0.0, 1e-12))
    r_ += 1

# ---------------- 世帯MC（10万本の経路から要約を数式で） ----------------
wp = wb.create_sheet("MC経路")
pc = list(P.columns)
for j, c in enumerate(pc):
    wp.cell(1, 1 + j, c).font = b
for r, row in enumerate(P.itertuples(index=False)):
    for j, v in enumerate(row):
        wp.cell(2 + r, 1 + j, float(v))
PRl = 1 + len(P)
pcol = {c: L(1 + j) for j, c in enumerate(pc)}
pr = lambda c: f"MC経路!${pcol[c]}$2:${pcol[c]}${PRl}"
wq = wb.create_sheet("MC要約")
for t, h in enumerate(["項目", "式", "Python", "差"]):
    wq.cell(1, 1 + t, h).font = b
q_ = 2
def addq(lab, f, pv, tol):
    global q_
    wq.cell(q_, 1, lab); wq.cell(q_, 2, "=" + f); wq.cell(q_, 3, float(pv)); wq.cell(q_, 4, f"=ABS(B{q_}-C{q_})/MAX(1,ABS(C{q_}))")
    checks.append((f"MC {lab}", "MC要約", f"D{q_}", 0.0, tol)); q_ += 1
for hz, H_, hit, dd in [(60, "H60", "hit60", "dd60"), (84, "H84", "hit84", "dd84")]:
    y = hz // 12
    addq(f"{y}年末 1億以上の確率", f'COUNTIF({pr(H_)},">="&100000000)/COUNT({pr(H_)})', MC.loc[hz, "1億以上"], 1e-12)
    addq(f"{y}年 一度でも1億の確率", f"AVERAGE({pr(hit)})", MC.loc[hz, "一度でも1億"], 1e-12)
    addq(f"{y}年末 世帯の中央値", f"MEDIAN({pr(H_)})", MC.loc[hz, "中央値"], 1e-9)
    addq(f"{y}年末 悪いほう10%", f"PERCENTILE({pr(H_)},0.1)", MC.loc[hz, "悪いほう10%"], 1e-9)
    addq(f"{y}年末 良いほう10%", f"PERCENTILE({pr(H_)},0.9)", MC.loc[hz, "良いほう10%"], 1e-9)
    addq(f"{y}年 途中で−30%超の確率", f'COUNTIF({pr(dd)},"<=-0.3")/COUNT({pr(dd)})', MC.loc[hz, "途中30超"], 1e-12)
    for acc, col in [("S2", f"W{hz}"), ("DC", f"D{hz}"), ("NISA", f"N{hz}")]:
        row = MA[(MA["期間"] == hz) & (MA["口座"] == acc)].iloc[0]
        addq(f"{y}年末 {acc}の中央値", f"MEDIAN({pr(col)})", row["中央値"], 1e-9)
        addq(f"{y}年末 {acc}の悪いほう10%", f"PERCENTILE({pr(col)},0.1)", row["悪いほう10"], 1e-9)

# ---------------- 突合の結果 ----------------
rs = wb.create_sheet("突合の結果", 0)
rs.append(["項目", "シート", "式の結果（差）", "Pythonの値（差の目標）", "差", "許容差", "判定"])
for i, (lab, sh, cell, pv, tol) in enumerate(checks):
    R = i + 2
    rs.cell(R, 1, lab); rs.cell(R, 2, sh); rs.cell(R, 3, f"='{sh}'!{cell}")
    rs.cell(R, 4, float(pv)); rs.cell(R, 5, f"=ABS(C{R}-D{R})"); rs.cell(R, 6, float(tol))
    rs.cell(R, 7, f'=IF(E{R}<=F{R},"一致","不一致")')
rs.cell(1, 9, "一致の数"); rs.cell(2, 9, f'=COUNTIF(G2:G{len(checks) + 1},"一致")')
rs.cell(1, 10, "項目数"); rs.cell(2, 10, len(checks))
fn = f"{OUT}/総合マニュアル_Excel突合.xlsx"
wb.save(fn)
print("saved", fn, "checks", len(checks))
