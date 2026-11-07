"""
DC規則の一斉比較 ③ のExcel突合ブック（Pythonの結果を、入力からExcel数式で独立に再計算して照合）
  1) 日次の売買：R0・R3・R11（010か預金の規則）を、010の日次リターンと○×から数式で再計算
     （月末の判定→翌営業日に売り→4営業日現金→買い、預金は6か月以上で年0.1%）→ 月次リターン全月・年率・最大下落
  2) 規則の選択：R6・R7・R10 の毎月の持ち物を、月末の基準価額から数式で（12ヶ月リターンの最大）
  3) R1・R2 の倍率＝実際の基準価額の倍率
  4) 世帯MCの集計：R0と上位2規則の10万本の5年末資産から、確率・分位点・確実性等価・対の標準誤差を数式で
  5) 世帯MCへの差し込み：DCの残高の経路（3本×60ヶ月）を月次リターンと掛金から数式で
  6) 判定：表の値から制約・採用条件・最終を数式で
使い方: python3 dc_excel.py → out_dc/DC規則の一斉比較_Excel突合.xlsx → LibreOfficeで再計算 → python3 dc_verify_excel.py
"""
import sys, json
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.utils import get_column_letter as L
import cmp_common as Q, s2x as X
import dc_engine as G

OUT = "out_dc"
dw = G.DCWorld()
MB = pd.read_csv(f"{OUT}/monthly_base.csv", index_col=0, parse_dates=True)
HH = pd.read_csv(f"{OUT}/household.csv")
GS = pd.read_csv(f"{OUT}/grid64_summary.csv").set_index("規則")
PD = json.load(open(f"{OUT}/pbo_dsr.json"))
DEC = json.load(open(f"{OUT}/decision.json"))
wb = Workbook()
checks = []

# ---------------- 1) 日次の売買 ----------------
cal = dw.cal
r010 = dw.R["010"].fillna(0.0)
i0 = int(cal.searchsorted(pd.Timestamp("2000-04-01")))
ds = wb.active; ds.title = "日次"
RULES1 = ["R0", "R3", "R11"]
hdr = ["日付", "010日次", "月末", "010価格(式)", "年月", "月初からの日数(式)"]
for k in RULES1:
    hdr += [f"{k}_保有(式)", f"{k}_日次(式)", f"{k}_NAV(式)"]
ds.append(hdr)
N = len(cal)
NL = N + 1
ms = wb.create_sheet("月次")
keys = sorted(set(d.year * 100 + d.month for d in cal))
MR = {kk: i + 2 for i, kk in enumerate(keys)}
ML = len(keys) + 1
dr = (1.001) ** (1 / 245) - 1
for i, d in enumerate(cal):
    R = i + 2
    ds.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    ds.cell(R, 2, float(r010.iloc[i]) if i > 0 else 0.0)
    ds.cell(R, 3, f"=IF(MONTH(A{R})<>MONTH(A{R+1}),1,0)" if i < N - 1 else "=1")
    ds.cell(R, 4, "=1" if i == 0 else f"=D{R-1}*(1+B{R})")
    ds.cell(R, 5, f"=YEAR(A{R})*100+MONTH(A{R})")
    ds.cell(R, 6, "=1" if i == 0 else f"=IF(C{R-1}=1,1,F{R-1}+1)")
    for j, k in enumerate(RULES1):
        c0 = 7 + 3 * j
        hc, rc, nc = L(c0), L(c0 + 1), L(c0 + 2)
        # 月次シートの列：P（今月効いている目標）, O（その前の目標）, 前月までの預金月数
        pc, oc, dc_ = {"R0": ("J", "K", "L"), "R3": ("M", "N", "O"), "R11": ("P", "Q", "R")}[k]
        if i < i0:
            ds.cell(R, c0, ""); ds.cell(R, c0 + 1, 0); ds.cell(R, c0 + 2, "")
            continue
        mrow = f"MATCH(E{R},月次!$A$2:$A${ML},0)"
        P = f"INDEX(月次!${pc}$2:${pc}${ML},{mrow})"
        O = f"INDEX(月次!${oc}$2:${oc}${ML},{mrow})"
        DMp = f"INDEX(月次!${dc_}$2:${dc_}${ML},{mrow}-1)"
        ds.cell(R, c0, f'=IF(F{R}<=1,{O},IF(F{R}<=5,IF({O}={P},{P},"CASH"),{P}))')
        ds.cell(R, c0 + 1, f'=IF({hc}{R}="010",B{R},IF({hc}{R}="DEP",IF({DMp}>=6,{dr!r},0),0))')
        ds.cell(R, c0 + 2, f"=1+{rc}{R}" if i == i0 else f"={nc}{R-1}*(1+{rc}{R})")
ms.append(["年月", "010月末価格(式)", "○(入力)", "10ヶ月平均(式)", "R3の判定(式)", "R0目標(式)", "R3目標(式)", "R11目標(式)", "",
           "R0_P", "R0_O", "R0_預金月数", "R3_P", "R3_O", "R3_預金月数", "R11_P", "R11_O", "R11_預金月数",
           "R0_月末NAV", "R3_月末NAV", "R11_月末NAV", "R0_月次(式)", "R3_月次(式)", "R11_月次(式)",
           "R0_月次(Py)", "R3_月次(Py)", "R11_月次(Py)", "R0差", "R3差", "R11差"])
st_by_key = {d.year * 100 + d.month: s for d, s in dw.state.items()}
start_key = cal[i0].year * 100 + cal[i0].month
for i, kk in enumerate(keys):
    R = i + 2
    ms.cell(R, 1, kk)
    ms.cell(R, 2, f"=SUMIFS(日次!$D$2:$D${NL},日次!$E$2:$E${NL},A{R},日次!$C$2:$C${NL},1)")
    s = st_by_key.get(kk)
    ms.cell(R, 3, "" if s is None or (isinstance(s, float)) else (1 if s in ("NORMAL", "DIP") else 0))
    ms.cell(R, 4, f"=AVERAGE(B{R-9}:B{R})" if i >= 9 else '=""')
    ms.cell(R, 5, f'=IF(D{R}="",1,IF(B{R}>D{R},1,0))')
    ms.cell(R, 6, f'=IF(C{R}=1,"010","DEP")')
    ms.cell(R, 7, f'=IF(E{R}=1,"010","DEP")')
    ms.cell(R, 8, f'=IF(AND(C{R}=1,E{R}=1),"010","DEP")')
    for (pc, oc, dcc, tc) in (("J", "K", "L", "F"), ("M", "N", "O", "G"), ("P", "Q", "R", "H")):
        if kk < start_key:
            ms[f"{pc}{R}"] = ""; ms[f"{oc}{R}"] = ""; ms[f"{dcc}{R}"] = 0
            continue
        ms[f"{pc}{R}"] = f"={tc}{R-1}"
        ms[f"{oc}{R}"] = f"={pc}{R}" if kk == start_key else f"={tc}{R-2}"
        ms[f"{dcc}{R}"] = f'=IF({pc}{R}="DEP",{dcc}{R-1}+1,0)'
    for j, k in enumerate(RULES1):
        nc = L(7 + 3 * j + 2)
        ms.cell(R, 19 + j, f"=SUMIFS(日次!${nc}$2:${nc}${NL},日次!$E$2:$E${NL},A{R},日次!$C$2:$C${NL},1)" if kk >= start_key else "")
        if kk > start_key:
            ms.cell(R, 22 + j, f"={L(19 + j)}{R}/{L(19 + j)}{R-1}-1")
            per = pd.Period(f"{kk // 100}-{kk % 100:02d}", "M").to_timestamp("M")
            v = MB[k].get(per, np.nan)
            if v == v:
                ms.cell(R, 25 + j, float(v))
                ms.cell(R, 28 + j, f"=ABS({L(22 + j)}{R}-{L(25 + j)}{R})")
for j, k in enumerate(RULES1):
    ms.cell(1, 32 + j, f"{k}_不一致の月数"); ms.cell(2, 32 + j, f'=COUNTIF({L(28 + j)}2:{L(28 + j)}{ML},">1E-9")')
    ms.cell(1, 35 + j, f"{k}_比べた月数"); ms.cell(2, 35 + j, f"=COUNT({L(28 + j)}2:{L(28 + j)}{ML})")
    checks.append((f"{k} 月次リターンの不一致の月数", "月次", f"{L(32 + j)}2", 0.0, 0.0))
    checks.append((f"{k} 比べた月数", "月次", f"{L(35 + j)}2", float(MB[k].notna().sum()), 0.0))
# 年率・最大下落（日次NAVから）
ix = wb.create_sheet("指標")
ix.append(["規則", "年率(式)", "年率(Py)", "最大下落(式)", "最大下落(Py)", "倍率(式)", "倍率(Py)"])
for j, k in enumerate(RULES1):
    R = j + 2
    nc = L(7 + 3 * j + 2)
    dd = L(16 + j)
    ds.cell(1, 16 + j, f"{k}_下落(式)")
    for i in range(i0, N):
        RR = i + 2
        ds.cell(RR, 16 + j, f"={nc}{RR}/MAX({nc}${i0 + 2}:{nc}{RR})-1")
    z = G.run_rule(dw, G.RULES[k])
    m = X.indicators(z["nav"])
    ix.cell(R, 1, k)
    ix.cell(R, 2, f"=(日次!{nc}{NL}/日次!{nc}{i0 + 2})^(1/((日次!A{NL}-日次!A{i0 + 2})/365.25))-1")
    ix.cell(R, 3, float(m["CAGR"]))
    ix.cell(R, 4, f"=MIN(日次!{dd}{i0 + 2}:{dd}{NL})")
    ix.cell(R, 5, float(m["MaxDD"]))
    ix.cell(R, 6, f"=日次!{nc}{NL}")
    ix.cell(R, 7, float(z["nav"].iloc[-1]))
    checks += [(f"{k} 年率", "指標", f"B{R}", float(m["CAGR"]), 1e-9), (f"{k} 最大下落", "指標", f"D{R}", float(m["MaxDD"]), 1e-9),
               (f"{k} 最終NAV", "指標", f"F{R}", float(z["nav"].iloc[-1]), 1e-9)]

# ---------------- 2) 規則の選択（R6・R7・R10） ----------------
sel = wb.create_sheet("選択")
C6 = ["006", "010", "037"]
C7 = ["006", "010", "037", "026", "012", "008"]
C10 = G.STOCKS_R10
cols = [("P", c) for c in C7] + [("R", c) for c in C10]
hdr = ["月末", "○"] + [f"{t}{c}" for t, c in cols] + [f"12M_{t}{c}(式)" for t, c in cols] + ["R6(式)", "R6(Py)", "R7(式)", "R7(Py)", "R10(式)", "R10(Py)", "R6一致", "R7一致", "R10一致"]
sel.append(hdr)
nc_ = len(cols)
ne = len(dw.me)
for k, d in enumerate(dw.me):
    R = k + 2
    sel.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    s = dw.state.iloc[k]
    sel.cell(R, 2, 1 if s in ("NORMAL", "DIP") else 0)
    for j, (t, c) in enumerate(cols):
        tab = dw.rme if (t == "R" or c == "026") else dw.pme
        v = tab[c].iloc[k]
        if v == v:
            sel.cell(R, 3 + j, float(v))
        cc = L(3 + j)
        sel.cell(R, 3 + nc_ + j, f'=IF(OR({cc}{R}="",{cc}{R-12}=""),"",{cc}{R}/{cc}{R-12}-1)' if k >= 12 else '=""')
    m0 = 3 + nc_
    rng7 = f"{L(m0)}{R}:{L(m0 + len(C7) - 1)}{R}"
    rng6 = f"{L(m0)}{R}:{L(m0 + 2)}{R}"
    rng10 = f"{L(m0 + len(C7))}{R}:{L(m0 + nc_ - 1)}{R}"
    nm6 = f"$C$1:${L(2 + 3)}$1"
    nm7 = f"$C$1:${L(2 + len(C7))}$1"
    nm10 = f"${L(3 + len(C7))}$1:${L(2 + nc_)}$1"
    b = 3 + 2 * nc_
    sel.cell(R, b, f'=IF(COUNT({rng6})=0,"010",IF(MAX({rng6})>0,MID(INDEX({nm6},MATCH(MAX({rng6}),{rng6},0)),2,3),"DEP"))')
    sel.cell(R, b + 2, f'=IF(COUNT({rng7})=0,"010",IF(MAX({rng7})>0,MID(INDEX({nm7},MATCH(MAX({rng7}),{rng7},0)),2,3),"DEP"))')
    sel.cell(R, b + 4, f'=IF(B{R}<>1,"DEP",IF(COUNT({rng10})=0,"010",MID(INDEX({nm10},MATCH(MAX({rng10}),{rng10},0)),2,3)))')
    for q, key in enumerate(("R6", "R7", "R10")):
        t = G.RULES[key][1](dw, k)
        sel.cell(R, b + 1 + 2 * q, list(t)[0])
        sel.cell(R, b + 6 + q, f"=IF({L(b + 2 * q)}{R}={L(b + 1 + 2 * q)}{R},1,0)")
b = 3 + 2 * nc_
for q, key in enumerate(("R6", "R7", "R10")):
    sel.cell(1, b + 10 + q, f"{key}_不一致の月数"); sel.cell(2, b + 10 + q, f"=COUNTIF({L(b + 6 + q)}2:{L(b + 6 + q)}{ne + 1},0)")
    checks.append((f"{key} 持ち物の選択の不一致の月数（{ne}ヶ月）", "選択", f"{L(b + 10 + q)}2", 0.0, 0.0))

# ---------------- 3) R1・R2 の倍率 ----------------
mt = wb.create_sheet("倍率")
mt.append(["規則", "投信", "開始日", "開始の基準価額", "最終日", "最終の基準価額", "倍率(式)", "倍率(Py)"])
for R, (k, c, st) in enumerate([("R1", "010", "2002-02-25"), ("R2", "003", "2000-04-01")], start=2):
    z = G.run_rule(dw, G.RULES[k], start=st)
    n = z["nav"]
    s = dw.nav[c]
    d0 = s.index[s.index < n.index[0]][-1]          # NAV初日の前日の基準価額（初日のリターンを含む）
    mt.append([k, c, str(d0.date()), float(s.loc[d0]), str(n.index[-1].date()), float(s.loc[n.index[-1]]), f"=F{R}/D{R}", float(n.iloc[-1])])
    checks.append((f"{k} 倍率＝{c}の基準価額の倍率", "倍率", f"G{R}", float(n.iloc[-1]), 1e-9))

# ---------------- 4) 世帯MCの集計 ----------------
_pz = np.load(f"{OUT}/paths_base.npz")
pz = {k: _pz[k] for k in _pz.files}      # 一度だけ読む
b5 = HH[HH.シナリオ == "基本"].set_index("規則")
top = [k for k in b5.sort_values("5年_1億以上", ascending=False).index if k != "R0"][:2]
mcK = ["R0"] + top
mcs = wb.create_sheet("MC集計")
n = len(pz["H60_R0"])
NR = n + 1
mcs.append([f"H60_{k}" for k in mcK] + [f"途中_{k}" for k in mcK] + [f"差_{k}" for k in top])
for i in range(n):
    R = i + 2
    row = [float(pz[f"H60_{k}"][i]) for k in mcK] + [float(pz[f"mindd60_{k}"][i]) for k in mcK]
    row += [f"=(B{R}>=100000000)-(A{R}>=100000000)", f"=(C{R}>=100000000)-(A{R}>=100000000)"][:len(top)]
    mcs.append(row)
ag = wb.create_sheet("MC指標")
ag.append(["規則", "5年1億(式)", "5年1億(Py)", "中央値(式)", "中央値(Py)", "悪いほう10%(式)", "悪いほう10%(Py)", "元本割れ(式)", "元本割れ(Py)",
           "途中50超(式)", "途中50超(Py)", "CE1(式)", "CE1(Py)", "CE3(式)", "CE3(Py)", "CE5(式)", "CE5(Py)", "確率差SE(式)", "確率差SE(Py)"])
for j, k in enumerate(mcK):
    R = j + 2
    c = L(1 + j); dcol = L(1 + len(mcK) + j)
    rg = f"MC集計!{c}2:{c}{NR}"
    ag.cell(R, 1, k)
    ag.cell(R, 2, f'=COUNTIF({rg},">=100000000")/COUNT({rg})'); ag.cell(R, 3, float(b5.loc[k, "5年_1億以上"]))
    ag.cell(R, 4, f"=MEDIAN({rg})"); ag.cell(R, 5, float(b5.loc[k, "5年_中央値"]))
    ag.cell(R, 6, f"=PERCENTILE({rg},0.1)"); ag.cell(R, 7, float(b5.loc[k, "5年_悪いほう10%"]))
    ag.cell(R, 8, f'=COUNTIF({rg},"<{Q.H0!r}")/COUNT({rg})'); ag.cell(R, 9, float(b5.loc[k, "5年_元本割れ"]))
    ag.cell(R, 10, f'=COUNTIF(MC集計!{dcol}2:{dcol}{NR},"<=-0.5")/COUNT({rg})'); ag.cell(R, 11, float(b5.loc[k, "5年_途中50超"]))
    ag.cell(R, 12, f"=EXP(SUMPRODUCT(LN({rg}/10000))/COUNT({rg}))*10000"); ag.cell(R, 13, float(b5.loc[k, "CE1"]))
    ag.cell(R, 14, f"=(SUMPRODUCT(({rg}/10000)^(-2))/COUNT({rg}))^(-1/2)*10000"); ag.cell(R, 15, float(b5.loc[k, "CE3"]))
    ag.cell(R, 16, f"=(SUMPRODUCT(({rg}/10000)^(-4))/COUNT({rg}))^(-1/4)*10000"); ag.cell(R, 17, float(b5.loc[k, "CE5"]))
    for col, nm, tol in ((2, "5年1億", 1e-12), (4, "中央値", 1e-3), (6, "悪いほう10%", 1e-3), (8, "元本割れ", 1e-12), (10, "途中50超", 1e-12),
                         (12, "CE1", 1e-3), (14, "CE3", 1e-3), (16, "CE5", 1e-3)):
        checks.append((f"{k} {nm}", "MC指標", f"{L(col)}{R}", float(ag.cell(R, col + 1).value), tol))
    if k != "R0":
        q = top.index(k)
        dcl = L(1 + 2 * len(mcK) + q)
        ag.cell(R, 18, f"=STDEV(MC集計!{dcl}2:{dcl}{NR})/SQRT(COUNT(MC集計!{dcl}2:{dcl}{NR}))")
        ag.cell(R, 19, float(b5.loc[k, "5年1億_差SE"]))
        checks.append((f"{k} 確率差の対の標準誤差", "MC指標", f"R{R}", float(b5.loc[k, "5年1億_差SE"]), 1e-12))

# ---------------- 5) 世帯MCへの差し込み（DCの残高の経路） ----------------
w = Q.World2("data")
T, S = Q.build_all(w, specs={"K0_予定どおり": Q.SPECS["K0_予定どおり"]})
TT = len(T)
lo = int(np.argmax(MB.reindex(T.index).notna().all(axis=1).values))
M = Q.draw_months(TT, 100_000, 84, seed=42, starts=np.arange(lo, TT - 11))
dp = wb.create_sheet("DC経路")
dp.append(["月", "行(0始まり)"] + [f"{k}_月次" for k in mcK] + [f"{k}_DC残高(式)" for k in mcK])
mt_ = wb.create_sheet("月次表")
mt_.append(["行", "月"] + mcK)
for t_ in range(TT):
    mt_.append([t_, str(T.index[t_].date())] + [float(np.nan_to_num(MB[k].reindex(T.index).iloc[t_])) for k in mcK])
r0 = 2
for pth in range(3):
    dp.cell(r0, 1, f"経路{pth}")
    r0 += 1
    first = r0
    for t_ in range(60):
        R = r0 + t_
        dp.cell(R, 1, t_ + 1); dp.cell(R, 2, int(M[pth, t_]))
        for j, k in enumerate(mcK):
            dp.cell(R, 3 + j, f"=INDEX(月次表!{L(3 + j)}$2:{L(3 + j)}${TT + 1},B{R}+1)")
            prev = f"{Q.D0!r}" if t_ == 0 else f"{L(3 + len(mcK) + j)}{R - 1}"
            dp.cell(R, 3 + len(mcK) + j, f"=({prev}+27500)*(1+{L(3 + j)}{R})")
    last = r0 + 59
    for j, k in enumerate(mcK):
        T2 = T.copy(); T2[Q.D1] = np.nan_to_num(MB[k].reindex(T.index).values)
        p = Q.household_mc(T2, S, Q.CANDS["A0"], months=60, M=M[pth:pth + 1, :60])
        checks.append((f"経路{pth} {k} 5年末のDC残高", "DC経路", f"{L(3 + len(mcK) + j)}{last}", float(p["D"][0]), 1e-4))
        # 経路の5年末の世帯資産も、本計算の10万本の同じ経路と一致すること
        checks.append((f"経路{pth} {k} 5年末の世帯資産＝本計算と同じ", "DC経路", f"{L(3 + len(mcK) + j)}{last}",
                       float(p["D"][0]), 1e-4))
        assert abs(float(p["H"][0]) - float(pz[f"H60_{k}"][pth])) < 1e-3, (k, pth)
    r0 = last + 2
# 重複の項目を除く（世帯資産の一致は上の assert で確認済み）
checks = [c for c in checks if "世帯資産＝本計算と同じ" not in c[0]]

# ---------------- 6) 判定 ----------------
dj = wb.create_sheet("判定")
ng = HH[HH.シナリオ == "ネガ寄せ"].set_index("規則")
cols = ["5年1億", "元本割れ", "途中50超", "確率差", "確率差SE", "CE1差", "CE1差SE", "CE3差", "CE3差SE", "CE5差", "CE5差SE",
        "ネガ寄せ確率差", "ネガ寄せCE1差", "ネガ寄せCE3差", "ネガ寄せCE5差", "64通りで高い"]
dj.append(["規則"] + cols + ["制約(式)", "確率(式)", "CE(式)", "ネガ寄せ(式)", "64通り(式)", "PBO(式)", "採用(式)", "順位用(式)"])
dj.cell(1, 27, "PBO"); dj.cell(2, 27, float(PD["PBO_世帯CSCV"]))
ks = G.ORDER
for i, k in enumerate(ks):
    R = i + 2
    v = [b5.loc[k, "5年_1億以上"], b5.loc[k, "5年_元本割れ"], b5.loc[k, "5年_途中50超"], b5.loc[k, "5年1億_差"], b5.loc[k, "5年1億_差SE"],
         b5.loc[k, "CE1_差"], b5.loc[k, "CE1_差SE"], b5.loc[k, "CE3_差"], b5.loc[k, "CE3_差SE"], b5.loc[k, "CE5_差"], b5.loc[k, "CE5_差SE"],
         ng.loc[k, "5年1億_差"], ng.loc[k, "CE1_差"], ng.loc[k, "CE3_差"], ng.loc[k, "CE5_差"], GS.loc[k, "R0より確率が高い"]]
    dj.cell(R, 1, k)
    for j, x in enumerate(v):
        dj.cell(R, 2 + j, float(x))
    dj.cell(R, 18, f"=IF(AND(C{R}<=C$2+1E-12,D{R}<=D$2+1E-12),1,0)")
    dj.cell(R, 19, f"=IF(E{R}>2*F{R},1,0)")
    dj.cell(R, 20, f"=IF(AND(G{R}>2*H{R},I{R}>2*J{R},K{R}>2*L{R}),1,0)")
    dj.cell(R, 21, f"=IF(AND(M{R}>=0,N{R}>=0,O{R}>=0,P{R}>=0),1,0)")
    dj.cell(R, 22, f"=IF(Q{R}>=33,1,0)")
    dj.cell(R, 23, "=IF($AA$2<0.5,1,0)")
    dj.cell(R, 24, "=0" if k == "R0" else f"=R{R}*S{R}*T{R}*U{R}*V{R}*W{R}")
    dj.cell(R, 25, f"=IF(X{R}=1,B{R},-1)")
NRd = len(ks) + 1
dj.cell(1, 29, "最終(式)"); dj.cell(2, 29, f'=IF(MAX(Y2:Y{NRd})<0,"R0",INDEX(A2:A{NRd},MATCH(MAX(Y2:Y{NRd}),Y2:Y{NRd},0)))')
dj.cell(1, 30, "最終(Py)"); dj.cell(2, 30, DEC["最終"])
dj.cell(1, 31, "一致"); dj.cell(2, 31, "=IF(AC2=AD2,1,0)")
dj.cell(1, 32, "採用条件を満たす数(式)"); dj.cell(2, 32, f"=SUM(X2:X{NRd})")
checks.append(("判定：最終の規則が一致（1＝一致）", "判定", "AE2", 1.0, 0.0))
checks.append(("判定：採用条件を満たす規則の数", "判定", "AF2", float(len(DEC["満たした規則"])), 0.0))

# ---------------- 突合の結果 ----------------
rs = wb.create_sheet("突合の結果", 0)
rs.append(["項目", "シート", "式の結果", "Pythonの値", "差", "許容差", "判定"])
for i, (lab, sh, cell, pv, tol) in enumerate(checks):
    R = i + 2
    rs.cell(R, 1, lab); rs.cell(R, 2, sh)
    rs.cell(R, 3, f"='{sh}'!{cell}")
    rs.cell(R, 4, float(pv)); rs.cell(R, 5, f"=ABS(C{R}-D{R})"); rs.cell(R, 6, float(tol))
    rs.cell(R, 7, f'=IF(E{R}<=F{R},"一致","不一致")')
rs.cell(1, 9, "一致の数"); rs.cell(2, 9, f'=COUNTIF(G2:G{len(checks) + 1},"一致")')
rs.cell(1, 10, "項目数"); rs.cell(2, 10, len(checks))
fn = f"{OUT}/DC規則の一斉比較_Excel突合.xlsx"
wb.save(fn)
print("saved", fn, "checks", len(checks), "MC上位", top)
