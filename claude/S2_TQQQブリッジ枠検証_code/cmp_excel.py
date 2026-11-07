"""
世帯の候補比較のExcel突合ブック（Pythonの結果を、入力からExcel数式で独立に再計算して照合）
  1) 12か月線：QQQの日次終値 → 月末終値 → 12ヶ月平均 → 上下の判定（Pythonの judg['sma'] と照合）
  2) 経路の再計算：A1・C3・D2 の各2本（84ヶ月）。月次の入力表（各濃さの月次リターン・売った割合・目標比率、DC・NISA）から、
     濃さの判定（到達度F・1段階）、床（TIPP）、売却割合、含み益の実現、損失の繰越（3年）、税、世帯資産、途中の下落、換金後を数式で
  3) MC集計：A0・A1・C3・D2 の10万本（基本）の経路別の値から、確率・分位点をCOUNTIF・PERCENTILEで再集計
  4) 投資指標：K0_遅れ・B1・C2の日次NAV（税引後・換金後）から年率・最大下落を数式で
  5) 判定：13候補の表から、制約・確率最大・選択を数式で
使い方: python3 cmp_excel.py → out_cmp/世帯候補比較_Excel突合.xlsx（LibreOfficeで再計算して cmp_verify_excel.py）
"""
import sys, json
sys.path.insert(0, ".")
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as L
import cmp_common as Q

OUT = "out_cmp"
w = Q.World2("data")
T, S = Q.build_all(w)
TT = len(T)
bold = Font(bold=True); hl = PatternFill("solid", fgColor="FFF2CC")
wb = Workbook()
checks = []        # (説明, シート, セル, Python値, 許容差)

# ---------------- 1) 12か月線 ----------------
ws = wb.active; ws.title = "QQQ日次"
q = w.mkt["qqq"].dropna()
q = q[q.index >= "1999-03-01"]
ws.append(["日付", "終値", "年月", "月末の行"])
n = len(q)
for i, (d, v) in enumerate(q.items()):
    R = i + 2
    ws.cell(R, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    ws.cell(R, 2, float(v))
    ws.cell(R, 3, f"=YEAR(A{R})*100+MONTH(A{R})")
    ws.cell(R, 4, f"=IF(C{R}<>C{R+1},1,0)" if i < n - 1 else "=1")
Rl = n + 1
js = w.judg["sma"]
sm = wb.create_sheet("12か月線")
sm.append(["年月", "月末終値(式)", "12ヶ月平均(式)", "判定(式)", "判定(Python)", "一致"])
keys = sorted(set(d.year * 100 + d.month for d in q.index))
ms = 0
for i, k in enumerate(keys):
    R = i + 2
    sm.cell(R, 1, k)
    sm.cell(R, 2, f"=SUMIFS(QQQ日次!$B$2:$B${Rl},QQQ日次!$C$2:$C${Rl},A{R},QQQ日次!$D$2:$D${Rl},1)")
    sm.cell(R, 3, f"=AVERAGE(B{R-11}:B{R})" if i >= 11 else '=""')
    sm.cell(R, 4, f'=IF(C{R}="","",IF(B{R}>C{R},"NORMAL","RETREAT"))')
    dd = [d for d in js.index if d.year * 100 + d.month == k]
    st = js.loc[dd[0], "state"] if dd else None
    sm.cell(R, 5, "" if st is None or (isinstance(st, float)) else st)
    sm.cell(R, 6, f'=IF(D{R}=E{R},1,0)')
    ms = R
sm.cell(1, 8, "不一致の月数"); sm.cell(2, 8, f"=COUNTIF(F2:F{ms},0)")
checks.append(("12か月線の判定（不一致の月数）", "12か月線", "H2", 0.0, 0.0))

# ---------------- 2) 月次の入力表 ----------------
SER = ["K0_遅れ", "K0_予定どおり", "K0_先行", "K0_到達"]
si = wb.create_sheet("系列")
si.cell(1, 1, "月の番号m").font = bold; si.cell(1, 2, "月末").font = bold
cols = {}
c0 = 3
for nm in SER:
    cols[nm] = c0
    si.cell(1, c0, nm).font = bold
    for k, h in enumerate(["r", "f"] + [f"w_{a}" for a in Q.ASSETS]):
        si.cell(2, c0 + k, h)
    c0 += 2 + len(Q.ASSETS)
mt = {"DC": T[Q.D1].values, "NISA": T["A_FANG"].values, "RET": (T["RET"].values > 0.5).astype(int), "TF": T["TF"].values.astype(int)}
for k, h in enumerate(mt):
    si.cell(1, c0 + k, h).font = bold
    cols[h] = c0 + k
for m in range(TT):
    R = m + 3
    si.cell(R, 1, m); si.cell(R, 2, T.index[m].to_pydatetime()).number_format = "yyyy-mm"
    for nm in SER:
        b = cols[nm]
        si.cell(R, b, float(S[nm]["r"][m])); si.cell(R, b + 1, float(S[nm]["f"][m]))
        for j in range(len(Q.ASSETS)):
            si.cell(R, b + 2 + j, float(S[nm]["wt"][m, j]))
    for h, arr in mt.items():
        si.cell(R, cols[h], float(arr[m]))
SR0, SR1 = 3, TT + 2
TAB = f"系列!$A${SR0}:${L(c0 + len(mt))}${SR1}"
HDR = f"系列!$A$1:${L(c0 + len(mt))}$1"

# 定数
cs = wb.create_sheet("定数")
consts = dict(G=Q.G, H0=Q.H0, W0=Q.W0, D0=Q.D0, N0=Q.N0, TAU=Q.TAU, B0=Q.W0 * (1 - Q.TODAY_W["GP"] * Q.GP_GAIN0), cDC=27_500, cN=50_000)
for i, (k, v) in enumerate(consts.items()):
    cs.cell(i + 1, 1, k); cs.cell(i + 1, 2, float(v))
CREF = {k: f"定数!$B${i + 1}" for i, k in enumerate(consts)}

# ---------------- 経路の再計算シート ----------------
M = np.load(f"{OUT}/M_base_84.npy")
HD = ["t", "m", "W前", "B前", "D前", "N前", "繰越3", "繰越2", "繰越1", "繰越0", "H月初", "到達線", "F", "目標の濃さ", "濃さ", "床λ",
      "使う系列", "倍率", "列", "r系列", "f系列"] + [f"新_{a}" for a in Q.ASSETS] + [f"前_{a}" for a in Q.ASSETS] + \
     ["投資比率前", "売った比率", "s", "実現割合", "実現益g", "使う3", "使う2", "使う1", "使う0", "税", "W税後", "B新",
      "繰越3後", "繰越2後", "繰越1後", "繰越0後", "W末", "D末", "N末", "H末", "高値", "下落", "最大下落", "含み益の税", "換金後H"]
CI = {h: i + 1 for i, h in enumerate(HD)}
C = {h: L(i + 1) for i, h in enumerate(HD)}


def replay_sheet(code, path, reach_liq=False):
    cand = Q.CANDS[code]
    ov = cand["overlay"]
    tag = code + ("_RL" if reach_liq else "")
    sh = wb.create_sheet(f"経路_{tag}_{path}")
    for h, j in CI.items():
        sh.cell(1, j, h).font = bold
    R0 = 2
    for t in range(84):
        R = R0 + t
        P = R - 1
        first = t == 0
        sh.cell(R, CI["t"], t); sh.cell(R, CI["m"], int(M[path, t]))
        # 前の値
        if first:
            sh.cell(R, CI["W前"], f"={CREF['W0']}"); sh.cell(R, CI["B前"], f"={CREF['B0']}")
            sh.cell(R, CI["D前"], f"={CREF['D0']}"); sh.cell(R, CI["N前"], f"={CREF['N0']}")
            for b in range(4):
                sh.cell(R, CI[f"繰越{b}"], 0)
        else:
            sh.cell(R, CI["W前"], f"={C['W末']}{P}"); sh.cell(R, CI["B前"], f"={C['B新']}{P}")
            sh.cell(R, CI["D前"], f"={C['D末']}{P}"); sh.cell(R, CI["N前"], f"={C['N末']}{P}")
            yb = f"AND({C['t']}{R}>0,MOD({C['t']}{R},12)=0)"
            sh.cell(R, CI["繰越3"], f"=IF({yb},{C['繰越2後']}{P},{C['繰越3後']}{P})")
            sh.cell(R, CI["繰越2"], f"=IF({yb},{C['繰越1後']}{P},{C['繰越2後']}{P})")
            sh.cell(R, CI["繰越1"], f"=IF({yb},{C['繰越0後']}{P},{C['繰越1後']}{P})")
            sh.cell(R, CI["繰越0"], f"=IF({yb},0,{C['繰越0後']}{P})")
        sh.cell(R, CI["H月初"], f"={C['W前']}{R}+{C['D前']}{R}+{C['N前']}{R}")
        H60c = f"{C['H末']}{R0 + 59}"
        G, H0 = CREF["G"], CREF["H0"]
        sh.cell(R, CI["到達線"], f"=IF({C['t']}{R}<60,{H0}*({G}/{H0})^({C['t']}{R}/60),IF({H60c}>={G},{G},{H60c}*({G}/{H60c})^(({C['t']}{R}-60)/24)))")
        sh.cell(R, CI["F"], f"={C['H月初']}{R}/{C['到達線']}{R}")
        if reach_liq:
            Hr = f"({C['H月初']}{R}-{CREF['TAU']}*MAX({C['W前']}{R}-{C['B前']}{R}-SUM({C['繰越3']}{R}:{C['繰越0']}{R}),0))"
        else:
            Hr = f"{C['H月初']}{R}"
        sh.cell(R, CI["目標の濃さ"], f"=IF({Hr}>={G},3,IF({C['F']}{R}<0.85,0,IF({C['F']}{R}>1.15,2,1)))")
        lvp = "1" if first else f"{C['濃さ']}{P}"
        if ov == "tipp_only":
            sh.cell(R, CI["濃さ"], f"=IF({C['目標の濃さ']}{R}=3,3,1)")
        else:
            sh.cell(R, CI["濃さ"], f"={lvp}+MAX(-1,MIN(1,{C['目標の濃さ']}{R}-{lvp}))")
        tipp = "tipp" in ov
        if tipp:
            sh.cell(R, CI["床λ"], f"=IF({C['濃さ']}{R}=3,INT(MAX(0,MIN(1,({C['H月初']}{R}-{G}-0.25*({C['D前']}{R}+{C['N前']}{R}))/MAX(0.25*{C['W前']}{R},1)))*4+1E-9)/4,1)")
        else:
            sh.cell(R, CI["床λ"], 1)
        levs = cand["sleeves"][0][1]
        if tipp:
            levs = (levs[0], levs[1], levs[2], levs[1])
        sh.cell(R, CI["使う系列"], f'=CHOOSE({C["濃さ"]}{R}+1,"{levs[0]}","{levs[1]}","{levs[2]}","{levs[3]}")')
        sh.cell(R, CI["倍率"], f"={C['床λ']}{R}")
        sh.cell(R, CI["列"], f"=MATCH({C['使う系列']}{R},{HDR},0)")
        mrow = f"{C['m']}{R}+1"
        sh.cell(R, CI["r系列"], f"=INDEX({TAB},{mrow},{C['列']}{R})")
        sh.cell(R, CI["f系列"], f"=INDEX({TAB},{mrow},{C['列']}{R}+1)")
        for j, a in enumerate(Q.ASSETS):
            sh.cell(R, CI[f"新_{a}"], f"={C['倍率']}{R}*INDEX({TAB},{mrow},{C['列']}{R}+2+{j})")
            if first:
                sh.cell(R, CI[f"前_{a}"], float(Q.TODAY_W.get(a, 0.0)))
            else:
                sh.cell(R, CI[f"前_{a}"], f"={C['新_' + a]}{P}")
        nw = f"{C['新_' + Q.ASSETS[0]]}{R}:{C['新_' + Q.ASSETS[-1]]}{R}"
        ow = f"{C['前_' + Q.ASSETS[0]]}{R}:{C['前_' + Q.ASSETS[-1]]}{R}"
        sh.cell(R, CI["投資比率前"], f"=SUM({ow})")
        sh.cell(R, CI["売った比率"], f"=SUMPRODUCT(({ow}-{nw}>0)*({ow}-{nw}))")
        sh.cell(R, CI["s"], f"=IF({C['投資比率前']}{R}>1E-12,{C['売った比率']}{R}/{C['投資比率前']}{R},0)")
        sh.cell(R, CI["実現割合"], f"=1-(1-MIN(1,MAX(0,{C['s']}{R})))*(1-{C['f系列']}{R})")
        sh.cell(R, CI["実現益g"], f"={C['実現割合']}{R}*({C['W前']}{R}-{C['B前']}{R})")
        gp = f"MAX({C['実現益g']}{R},0)"
        sh.cell(R, CI["使う3"], f"=MIN({C['繰越3']}{R},{gp})")
        sh.cell(R, CI["使う2"], f"=MIN({C['繰越2']}{R},{gp}-{C['使う3']}{R})")
        sh.cell(R, CI["使う1"], f"=MIN({C['繰越1']}{R},{gp}-{C['使う3']}{R}-{C['使う2']}{R})")
        sh.cell(R, CI["使う0"], f"=MIN({C['繰越0']}{R},{gp}-{C['使う3']}{R}-{C['使う2']}{R}-{C['使う1']}{R})")
        sh.cell(R, CI["税"], f"={CREF['TAU']}*({gp}-{C['使う3']}{R}-{C['使う2']}{R}-{C['使う1']}{R}-{C['使う0']}{R})")
        sh.cell(R, CI["W税後"], f"={C['W前']}{R}-{C['税']}{R}")
        sh.cell(R, CI["B新"], f"={C['B前']}{R}+{C['実現益g']}{R}-{C['税']}{R}")
        for b in (3, 2, 1):
            sh.cell(R, CI[f"繰越{b}後"], f"={C['繰越' + str(b)]}{R}-{C['使う' + str(b)]}{R}")
        sh.cell(R, CI["繰越0後"], f"={C['繰越0']}{R}-{C['使う0']}{R}+MAX(-{C['実現益g']}{R},0)")
        sh.cell(R, CI["W末"], f"={C['W税後']}{R}*(1+{C['倍率']}{R}*{C['r系列']}{R})")
        sh.cell(R, CI["D末"], f"=({C['D前']}{R}+{CREF['cDC']})*(1+INDEX({TAB},{mrow},{cols['DC']}))")
        sh.cell(R, CI["N末"], f"=({C['N前']}{R}+{CREF['cN']})*(1+INDEX({TAB},{mrow},{cols['NISA']}))")
        sh.cell(R, CI["H末"], f"={C['W末']}{R}+{C['D末']}{R}+{C['N末']}{R}")
        sh.cell(R, CI["高値"], f"=MAX({H0},{C['H末']}{R})" if first else f"=MAX({C['高値']}{P},{C['H末']}{R})")
        sh.cell(R, CI["下落"], f"={C['H末']}{R}/{C['高値']}{R}-1")
        sh.cell(R, CI["最大下落"], f"=MIN(0,{C['下落']}{R})" if first else f"=MIN({C['最大下落']}{P},{C['下落']}{R})")
        sh.cell(R, CI["含み益の税"], f"={CREF['TAU']}*MAX({C['W末']}{R}-{C['B新']}{R}-SUM({C['繰越3後']}{R}:{C['繰越0後']}{R}),0)")
        sh.cell(R, CI["換金後H"], f"={C['H末']}{R}-{C['含み益の税']}{R}")
    pz = np.load(f"{OUT}/paths_{tag}.npz")
    r59, r83 = R0 + 59, R0 + 83
    nm = sh.title
    code = tag
    checks.append((f"{code} 経路{path} 5年末の世帯資産", nm, f"{C['H末']}{r59}", float(pz["H60"][path]), 0.01))
    checks.append((f"{code} 経路{path} 5年末の換金後", nm, f"{C['換金後H']}{r59}", float(pz["H60L"][path]), 0.01))
    checks.append((f"{code} 経路{path} 5年の最大下落", nm, f"{C['最大下落']}{r59}", float(pz["mindd60"][path]), 1e-9))
    checks.append((f"{code} 経路{path} 7年末の世帯資産", nm, f"{C['H末']}{r83}", float(pz["H84"][path]), 0.01))
    checks.append((f"{code} 経路{path} 7年の税の合計", nm, f"SUM_TAX", float(pz["tax"][path]), 0.01))
    sh.cell(1, len(HD) + 2, "7年の税の合計"); sh.cell(2, len(HD) + 2, f"=SUM({C['税']}{R0}:{C['税']}{r83})")
    checks[-1] = (checks[-1][0], nm, f"{L(len(HD) + 2)}2", checks[-1][3], 0.01)


# 経路は「到達」「遅れ」を通るものを選ぶ（確かめる意味のある経路）
pzA1 = np.load(f"{OUT}/paths_A1.npz")
p_list = {}
for code in ("A1", "C3", "D2"):
    pz = np.load(f"{OUT}/paths_{code}.npz")
    hi = [i for i in range(len(M)) if pz["H60"][i] >= 1e8][:1]
    lo = [i for i in range(len(M)) if pz["H60"][i] < 0.8e8][:1]
    p_list[code] = hi + lo
    for pth in p_list[code]:
        replay_sheet(code, pth)
# 最終候補 D2（到達を換金後で判定）：定義の違いで結果が変わる経路と、到達する経路
a = np.load(f"{OUT}/paths_D2.npz"); b = np.load(f"{OUT}/paths_D2_RL.npz")
diff = [i for i in range(len(M)) if abs(a["H84"][i] - b["H84"][i]) > 1][:1]
hi = [i for i in range(len(M)) if b["H60"][i] >= 1e8 and i not in diff][:1]
p_list["D2_RL"] = diff + hi
for pth in p_list["D2_RL"]:
    replay_sheet("D2", pth, reach_liq=True)

# ---------------- 3) MC集計（10万本） ----------------
mc = wb.create_sheet("MC集計")
hh = pd.read_csv(f"{OUT}/household.csv")
b5 = hh[(hh.シナリオ == "基本") & (hh.期間 == 60)].set_index("候補")
b7 = hh[(hh.シナリオ == "基本") & (hh.期間 == 84)].set_index("候補")
codes = ["A0", "A1", "C3", "D2", "C3_RL", "D2_RL"]
hl_ = pd.read_csv(f"{OUT}/reachliq_household.csv")
for code_ in ("C3", "D2"):
    for hz, df_ in ((60, b5), (84, b7)):
        row = hl_[(hl_.シナリオ == "基本") & (hl_.期間 == hz) & (hl_.候補 == code_)].iloc[0]
        df_.loc[code_ + "_RL"] = row.reindex(df_.columns)
mc.cell(1, 1, "経路");
for j, code in enumerate(codes):
    pz = np.load(f"{OUT}/paths_{code}.npz")
    b = 2 + j * 4
    for k, (h, arr) in enumerate([("H60", pz["H60"]), ("H60L", pz["H60L"]), ("mindd60", pz["mindd60"]), ("H84", pz["H84"])]):
        mc.cell(1, b + k, f"{code}_{h}").font = bold
        for i, v in enumerate(arr):
            mc.cell(i + 2, b + k, float(v))
NP = len(np.load(f"{OUT}/paths_A1.npz")["H60"])
ag = wb.create_sheet("MC集計の式")
ag.append(["候補", "1億以上(式)", "1億以上(Python)", "元本割れ(式)", "元本割れ(Python)", "途中50超(式)", "途中50超(Python)",
           "悪いほう10%(式)", "悪いほう10%(Python)", "中央値(式)", "中央値(Python)", "1億以上の平均(式)", "1億以上の平均(Python)",
           "換金後1億以上(式)", "換金後1億以上(Python)", "7年1億以上(式)", "7年1億以上(Python)"])
for j, code in enumerate(codes):
    R = j + 2
    b = 2 + j * 4
    cH, cL, cD, c7 = (f"MC集計!${L(b + k)}$2:${L(b + k)}${NP + 1}" for k in range(4))
    G, H0 = CREF["G"], CREF["H0"]
    f = [f'=COUNTIF({cH},">="&{G})/{NP}', f'=COUNTIF({cH},"<"&{H0})/{NP}', f'=COUNTIF({cD},"<="&-0.5)/{NP}',
         f"=PERCENTILE({cH},0.1)", f"=MEDIAN({cH})", f'=AVERAGEIF({cH},">="&{G})', f'=COUNTIF({cL},">="&{G})/{NP}',
         f'=COUNTIF({c7},">="&{G})/{NP}']
    py = [b5.loc[code, "1億以上"], b5.loc[code, "元本割れ"], b5.loc[code, "途中50超"], b5.loc[code, "悪いほう10%"],
          b5.loc[code, "中央値"], b5.loc[code, "1億以上の平均"], b5.loc[code, "換金後1億以上"], b7.loc[code, "1億以上"]]
    ag.cell(R, 1, code)
    labs = ["1億以上", "元本割れ", "途中50超", "悪いほう10%", "中央値", "1億以上の平均", "換金後1億以上", "7年1億以上"]
    for k, (ff, pv) in enumerate(zip(f, py)):
        ag.cell(R, 2 + 2 * k, ff); ag.cell(R, 3 + 2 * k, float(pv))
        tol = 1e-9 if k in (0, 1, 2, 6, 7) else 0.5
        checks.append((f"MC集計 {code} {labs[k]}", "MC集計の式", f"{L(2 + 2 * k)}{R}", float(pv), tol))

# ---------------- 4) 投資指標（日次NAV） ----------------
si_df = pd.read_csv(f"{OUT}/series_indicators.csv").set_index("持ち方")
nv = wb.create_sheet("日次NAV")
names = ["K0_遅れ", "B1", "C2_予定どおり"]
navs = {}
for nm in names:
    z = Q.run_series(w, Q.SPECS[nm], pretax=False)
    navs[nm] = z["nav"]; navs[nm + "_換金後"] = z["res"]["nav_liq"]
keys_ = list(navs)
dates = navs[names[0]].index
nv.cell(1, 1, "日付")
for j, k in enumerate(keys_):
    nv.cell(1, 2 + j, k).font = bold
for i, d in enumerate(dates):
    nv.cell(i + 2, 1, d.to_pydatetime()).number_format = "yyyy-mm-dd"
    for j, k in enumerate(keys_):
        nv.cell(i + 2, 2 + j, float(navs[k].iloc[i]))
ND = len(dates) + 1
ix = wb.create_sheet("指標の式")
ix.append(["系列", "年率(式)", "年率(Python)", "最大下落(式)", "最大下落(Python)"])
# 最大下落は「高値からの下落」の補助列を日次NAVシートに作る
for j, k in enumerate(keys_):
    c = L(2 + j); h = L(2 + len(keys_) + j)
    nv.cell(1, 2 + len(keys_) + j, k + "_下落")
    for i in range(len(dates)):
        R = i + 2
        nv.cell(R, 2 + len(keys_) + j, f"={c}{R}/MAX({c}$2:{c}{R})-1")
for j, k in enumerate(keys_):
    R = j + 2
    c = L(2 + j); h = L(2 + len(keys_) + j)
    ix.cell(R, 1, k)
    ix.cell(R, 2, f"=(日次NAV!{c}{ND}/日次NAV!{c}2)^(1/((日次NAV!A{ND}-日次NAV!A2)/365.25))-1")
    ix.cell(R, 4, f"=MIN(日次NAV!{h}2:{h}{ND})")
    base = k.replace("_換金後", "")
    py_c = si_df.loc[base, "換金後年率" if k.endswith("_換金後") else "年率"]
    py_d = si_df.loc[base, "換金後最大下落" if k.endswith("_換金後") else "最大下落"]
    ix.cell(R, 3, float(py_c)); ix.cell(R, 5, float(py_d))
    checks.append((f"{k} 年率", "指標の式", f"B{R}", float(py_c), 1e-9))
    checks.append((f"{k} 最大下落", "指標の式", f"D{R}", float(py_d), 1e-9))

# ---------------- 5) 判定 ----------------
dj = wb.create_sheet("判定")
dj.append(["候補", "1億以上", "元本割れ", "途中50超", "1億以上の平均", "制約を満たす(式)", "順位用(式)"])
allc = [c for c in b5.index if not str(c).endswith("_RL")]
for i, c in enumerate(allc):
    R = i + 2
    dj.cell(R, 1, c)
    for k, col in enumerate(["1億以上", "元本割れ", "途中50超", "1億以上の平均"]):
        dj.cell(R, 2 + k, float(b5.loc[c, col]))
rA1 = allc.index("A1") + 2
NR = len(allc) + 1
for i, c in enumerate(allc):
    R = i + 2
    dj.cell(R, 6, f"=IF(AND(C{R}<=C${rA1}+1E-12,D{R}<=D${rA1}+1E-12),1,0)")
    dj.cell(R, 7, f"=IF(F{R}=1,B{R},-1)")
dj.cell(1, 9, "選択(式)"); dj.cell(2, 9, f"=INDEX(A2:A{NR},MATCH(MAX(G2:G{NR}),G2:G{NR},0))")
dj.cell(1, 10, "選択(Python)"); dj.cell(2, 10, json.load(open(f"{OUT}/decision_main.json"))["事後を含む13"]["選択_関門前"])
dj.cell(1, 11, "一致"); dj.cell(2, 11, "=IF(I2=J2,1,0)")
checks.append(("判定：選択が一致（1＝一致）", "判定", "K2", 1.0, 0.0))

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
fn = f"{OUT}/世帯候補比較_Excel突合.xlsx"
wb.save(fn)
json.dump(dict(paths=p_list, n_checks=len(checks)), open(f"{OUT}/excel_meta.json", "w"), ensure_ascii=False)
print("saved", fn, "checks", len(checks), "paths", p_list)
