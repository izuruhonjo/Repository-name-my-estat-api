"""
世帯の候補比較（2026-11-07）の共通部品。候補と判定は cmp_prereg.py（結果を見る前に固定）
-----------------------------------------------------------------------------------------
1. S2口座の各「持ち方」（濃さ・エンジン）を正典エンジンK0（s2x.py）で日次バックテスト
   ・税引前（TAX=0）で回し、月次リターン r、その月に売った割合 f（含み益の実現割合）、月初の目標比率 wt を取る
   ・税は世帯MCの中で経路ごとの取得額から計算する（同じ物差し）
2. 世帯MC（S2口座＋DC④＋NISA）：12ヶ月ブロック・ブートストラップ、濃さは月1回・1段階、
   5年の到達線→5年末に未達なら残り2年で引き直し、暴落ストレス（1日−20%など）
"""
from __future__ import annotations
import sys, re, math
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import s2engine as E, s2x as X, hh, imp_common as C

G = 1e8                      # 目標 1億円
TAU = 0.20315                # 譲渡益税
W0, D0, N0 = C.W0, C.D0, C.N0
H0 = W0 + D0 + N0            # 4,858.6万円★（11/6実額起点）
D1 = C.D1
TODAY_W = {"GP": 0.5, "CASH": 0.5}   # 11/9約定後のS2口座（ブレーキで半分売却）
GP_GAIN0 = 0.35              # ★ゴールドプラスの含み益÷評価額（仮定。感応度 0・0.5）
ASSETS = ["GP", "N1", "SV", "TQQQ", "QLD", "IEFJ"]      # 投資している資産（円現金は含めない）
JUMP_BETA = {"GP": 1.0, "N1": 1.0, "SV": 0.2, "TQQQ": 3.0, "QLD": 2.0, "IEFJ": 0.0}
LEVELS = ("遅れ", "予定どおり", "先行", "到達")


# =============================================================
# 1. 市場データと判定
# =============================================================
class World2(C.World):
    """C.World に12か月線の判定（judg['sma']）と、月末QQQ・12ヶ月平均を足す。"""

    def __init__(self, data="data"):
        super().__init__(data)
        jb = self.judg["base"]
        me = jb.index
        q = self.mkt["qqq"].loc[me]
        sma = q.rolling(12).mean()                       # 当月を含む12ヶ月平均（検証ブランチと同じ定義）
        js = jb.copy()
        js["state"] = [None if pd.isna(s) else ("NORMAL" if qq > s else "RETREAT") for qq, s in zip(q.values, sma.values)]
        self.judg["sma"] = js
        extra = {"qqq_me": q, "qqq_sma12": sma}
        for k in ("base", "sma"):
            self.ctx[k] = X.month_ctx_table(self.mkt, self.assets, self.judg[k], extra)
        self.qme, self.sma12 = q, sma


# =============================================================
# 2. 持ち方（policy）。×（RETREAT）はK0の守り待避（XLU50+IEF50 か 円現金）
# =============================================================
def _retreat(c):
    return X.default_policy({**c, "state": "RETREAT"})


def k0_level(level):
    """G5の仕様（目標ルールの濃さ）。予定どおり＝K0そのもの。"""
    def p(c):
        st = c["state"]
        if st == "RETREAT":
            return _retreat(c)
        if level == "遅れ":
            return {"GP": .5, "TQQQ": .5} if st == "NORMAL" else {"N1": .5, "QLD": .5}
        if level == "予定どおり":
            return {"GP": 1.0} if st == "NORMAL" else {"N1": 1.0}
        if level == "先行":
            return {"GP": .2, "N1": .8} if st == "NORMAL" else {"N1": 1.0}
        if level == "到達":
            return {"N1": .5, "CASH": .5}
        raise ValueError(level)
    return p


def sma_level(level, off="CASH"):
    """12か月線の3倍NASDAQ（judg='sma' で使う：NORMAL＝12ヶ月平均の上）。"""
    def p(c):
        if c["state"] != "NORMAL":
            return {off: 1.0}
        if level in ("遅れ", "予定どおり"):
            return {"TQQQ": 1.0}
        if level == "先行":
            return {"TQQQ": .6, "CASH": .4}
        if level == "到達":
            return {"N1": .5, "CASH": .5}
        raise ValueError(level)
    return p


def vt_level(level, sigma=0.25):
    """C2：12か月線の上ならTQQQをボラ目標で（比率＝σ*÷(3×QQQの20日ボラ)、10%刻み、上限1）、下なら守り待避。"""
    mult = {"遅れ": 1.25, "予定どおり": 1.0, "先行": 0.6}

    def p(c):
        if c["state"] != "NORMAL":
            return _retreat(c)
        if level == "到達":
            return {"N1": .5, "CASH": .5}
        rv = c.get("rv")
        if rv is None or not (rv == rv) or rv <= 0:
            w = 1.0
        else:
            w = min(1.0, round(sigma * mult[level] / (3.0 * rv) * 10) / 10)
        if w >= 1.0:
            return {"TQQQ": 1.0}
        if w <= 0.0:
            return {"CASH": 1.0}
        return {"TQQQ": w, "CASH": 1 - w}
    return p


K0CFG = dict(keep_brake_on_switch=True)
SPECS = {
    # K0 と目標ルールの濃さ（G5の仕様）
    "K0_遅れ": dict(policy=k0_level("遅れ"), cfg=K0CFG, judg="base"),
    "K0_予定どおり": dict(policy=None, cfg=K0CFG, judg="base"),          # ＝K0（正典）そのもの
    "K0_先行": dict(policy=k0_level("先行"), cfg=K0CFG, judg="base"),
    "K0_到達": dict(policy=k0_level("到達"), cfg=K0CFG, judg="base"),
    # 12か月線の3倍NASDAQ（ブレーキなし＝検証ブランチの定義どおり）
    "B1": dict(policy=sma_level("予定どおり", "CASH"), cfg=dict(vol_brake=False), judg="sma"),
    "B2": dict(policy=sma_level("予定どおり", "N1"), cfg=dict(vol_brake=False), judg="sma"),
    "B_先行": dict(policy=sma_level("先行", "CASH"), cfg=dict(vol_brake=False), judg="sma"),
    "B_到達": dict(policy=sma_level("到達", "CASH"), cfg=dict(vol_brake=False), judg="sma"),
    # C2：ボラ目標TQQQ（K0のブレーキ付き）
    "C2_遅れ": dict(policy=vt_level("遅れ"), cfg=K0CFG, judg="sma"),
    "C2_予定どおり": dict(policy=vt_level("予定どおり"), cfg=K0CFG, judg="sma"),
    "C2_先行": dict(policy=vt_level("先行"), cfg=K0CFG, judg="sma"),
    "C2_到達": dict(policy=vt_level("到達"), cfg=K0CFG, judg="sma"),
}

A1L = ("K0_遅れ", "K0_予定どおり", "K0_先行", "K0_到達")
CANDS = {
    "A0": dict(name="K0（目標ルールなし）", sleeves=[(1.0, ("K0_予定どおり",) * 4)], overlay="none"),
    "A1": dict(name="K0＋目標ルール（遅れたらTQQQ）＝専門家の選択", sleeves=[(1.0, A1L)], overlay="goal"),
    "A2": dict(name="K0＋目標ルール（TQQQなし）", sleeves=[(1.0, ("K0_予定どおり", "K0_予定どおり", "K0_先行", "K0_到達"))], overlay="goal"),
    "B1": dict(name="12か月線の3倍NASDAQ（下は円現金）", sleeves=[(1.0, ("B1",) * 4)], overlay="none"),
    "B2": dict(name="12か月線の3倍NASDAQ（下は1倍）", sleeves=[(1.0, ("B2",) * 4)], overlay="none"),
    "B3": dict(name="12か月線の3倍NASDAQ＋目標ルール", sleeves=[(1.0, ("B1", "B1", "B_先行", "B_到達"))], overlay="goal"),
    "C1": dict(name="A1＋遅れのTQQQは12か月線の上だけ", sleeves=[(1.0, A1L)], overlay="goal_tf"),
    "C2": dict(name="ボラ目標TQQQ（12か月線＋ブレーキ）＋目標ルール",
               sleeves=[(1.0, ("C2_遅れ", "C2_予定どおり", "C2_先行", "C2_到達"))], overlay="goal"),
    "C3": dict(name="A1＋到達後は床つき（TIPP）", sleeves=[(1.0, A1L)], overlay="goal_tipp"),
    "C4": dict(name="C1＋C3", sleeves=[(1.0, A1L)], overlay="goal_tf_tipp"),
    "C5": dict(name="コア75%（A1）＋サテライト25%（12か月線TQQQ）",
               sleeves=[(0.75, A1L), (0.25, ("B1", "B1", "B1", "CASH"))], overlay="goal"),
}
# 事後の候補（11/7、本計算の要因分解を見たあとに追加。PBO・DSRの試行数に数える）
#  分解の結論：前回比の低下は「先行・到達」の持ち物（金を外しNASDAQに寄せる）が主因。到達後は床つきで守る方が確率が上がり、
#  「遅れたらTQQQ」は途中−50%超・元本割れを増やす。→ TQQQを使わず、到達後の床だけを足す2案
CANDS_POST = {
    "D1": dict(name="事後：A2（TQQQなし）＋到達後は床つき", sleeves=[(1.0, ("K0_予定どおり", "K0_予定どおり", "K0_先行", "K0_到達"))],
               overlay="goal_tipp"),
    "D2": dict(name="事後：K0のまま、1億に届いたら床つき（それ以外の濃さは使わない）", sleeves=[(1.0, ("K0_予定どおり",) * 4)],
               overlay="tipp_only"),
}
CANDS.update(CANDS_POST)
ORDER_PRE = [k for k in CANDS if k not in CANDS_POST]
ORDER = list(CANDS)


# =============================================================
# 3. 日次バックテスト → 月次の r, f, wt
# =============================================================
_LOG = []
_orig_sell = E.Account.sell


def _logged_sell(self, asset, frac, px, date, i, is_fund):
    p = self.pos.get(asset)
    if p and p["units"] > 0 and frac > 0:
        inv = sum(q["units"] * px[k] for k, q in self.pos.items())
        _LOG.append((date, inv, p["units"] * frac * px[asset]))
    return _orig_sell(self, asset, frac, px, date, i, is_fund)


def _parse_core(s):
    out = {}
    for part in s.split("+"):
        m = re.match(r"(.*)(\d\.\d\d)$", part)
        out[m.group(1)] = float(m.group(2))
    return out


def run_series(w: World2, spec: dict, pretax=True, **over):
    """返り値：dict(r=月次リターン, f=実現割合, wt=月初目標比率(DataFrame), nav=日次NAV, res=simulate_xの結果)"""
    global _LOG
    _LOG = []
    E.Account.sell = _logged_sell
    old = E.TAX
    if pretax:
        E.TAX = 0.0
    try:
        res = w.run({**spec["cfg"], **over}, spec["policy"], jkey=spec["judg"])
    finally:
        E.TAX = old
        E.Account.sell = _orig_sell
    nav = res["nav"]
    mr = nav.resample("ME").last().pct_change().dropna()
    # 実現割合：日ごとに（売却額の合計÷その日最初の売却直前の投資額）、月で 1−Π(1−f)
    per = mr.index.to_period("M")
    f = pd.Series(0.0, index=mr.index)
    if _LOG:
        lg = pd.DataFrame(_LOG, columns=["date", "inv", "sold"])
        day = lg.groupby("date").agg(inv=("inv", "first"), sold=("sold", "sum"))
        fd = (day["sold"] / day["inv"]).clip(0, 1)
        fm = 1 - (1 - fd).groupby(pd.DatetimeIndex(fd.index).to_period("M")).prod()
        f = pd.Series(fm.reindex(per).fillna(0.0).values, index=mr.index)
    # 月初（各月の最初の営業日）の目標比率
    st = res["states"]
    first = st.groupby(st.index.to_period("M")).head(1)
    wt = pd.DataFrame([_parse_core(c) for c in first["core"]], index=pd.DatetimeIndex(first.index).to_period("M")).fillna(0.0)
    for a in ASSETS + ["CASH"]:
        if a not in wt:
            wt[a] = 0.0
    wt = wt.reindex(per)
    wt.index = mr.index
    return dict(r=mr, f=f, wt=wt[ASSETS], nav=nav, res=res)


def month_table(w: World2):
    """世帯MCの月次表（DC④・NISA・K0の×・12か月線の上下）。hh.build_month_table と同じ月。"""
    r0 = w.run(dict(keep_brake_on_switch=True))
    T = hh.build_month_table(r0["nav"], r0["states"], {D1: w.dc("base")}, w.A, rate_daily=w.mkt["rate"])
    js = w.judg["sma"]["state"]
    tf_end = pd.Series((js == "NORMAL").values, index=js.index.to_period("M"))     # 月末時点の判定
    per = T.index.to_period("M")
    T["TF"] = [bool(tf_end.get(p - 1, False)) for p in per]                           # その月の初めに効いている判定
    return T, r0


def build_all(w: World2, specs=SPECS, **over):
    """全シリーズを作り、月次表に揃える。返り値 (T, S)：S[name]=dict(r,f,wt) は T.index に揃えた ndarray"""
    T, r0 = month_table(w)
    S = {}
    for name, sp in specs.items():
        z = run_series(w, sp, pretax=True, **over)
        idx = T.index
        S[name] = dict(r=z["r"].reindex(idx).values, f=z["f"].reindex(idx).values,
                       wt=z["wt"].reindex(idx).fillna(0.0).values)
        assert not np.isnan(S[name]["r"]).any(), name
    n = len(T)
    S["CASH"] = dict(r=np.zeros(n), f=np.zeros(n), wt=np.zeros((n, len(ASSETS))))
    return T, S


# =============================================================
# 4. 世帯MC
# =============================================================
def draw_months(TT, n, months, seed=42, weights=None, starts=None, block=12):
    rng = np.random.default_rng(seed)
    if starts is None:
        starts = np.arange(0, TT - block + 1)
    starts = np.asarray(starts)
    p = None
    if weights is not None:
        wv = np.asarray(weights, float)[starts]
        p = wv / wv.sum()
    nb = math.ceil(months / block)
    pick = rng.choice(starts, size=(n, nb), p=p)
    return np.concatenate([pick[:, k][:, None] + np.arange(block) for k in range(nb)], axis=1)[:, :months]


def scen_kw(T, scen):
    """シナリオ → draw_months の引数。"""
    TT = len(T)
    if scen == "基本":
        return {}
    if scen == "ネガ寄せ":
        return dict(weights=E.negative_tilt_weights(T["S2"]))
    if scen == "直近":
        lo = int(np.searchsorted(T.index, pd.Timestamp("2013-01-01")))
        return dict(starts=np.arange(lo, TT - 12 + 1))
    raise ValueError(scen)


def household_mc(T, S, cand, months=60, n=100_000, seed=42, scen="基本", M=None, jump=None,
                 gp_gain0=GP_GAIN0, cDC=27_500, cN=50_000, return_paths=False, tax=True, one_step=True,
                 reach_liq=False, record=False, snap=False):
    """
    cand: CANDS の要素。jump: None か dict(p=月あたり確率, J=NASDAQ100の1日の下落率(負), total_loss=TQQQ全損か)
    7年（months=84）は「5年の到達線→5年末に未達なら残り2年で引き直し」。
    """
    TT = len(T)
    tax_on = tax
    if M is None:
        M = draw_months(TT, n, months, seed=seed, **scen_kw(T, scen))
    n = M.shape[0]
    names = list(S)
    sid = {k: i for i, k in enumerate(names)}
    R = np.stack([S[k]["r"] for k in names])          # (nS, TT)
    Fr = np.stack([S[k]["f"] for k in names])
    WT = np.stack([S[k]["wt"] for k in names])        # (nS, TT, nA)
    dc = T[D1].values; nis = T["A_FANG"].values; ret = T["RET"].values > 0.5; tf = T["TF"].values.astype(bool)
    ov = cand["overlay"]
    goal = ov.startswith("goal") or ov == "tipp_only"
    tipp_only = ov == "tipp_only"
    use_tf = "tf" in ov
    use_tipp = "tipp" in ov
    sl = cand["sleeves"]
    nsl = len(sl)
    lev_ids = [np.array([sid[x] for x in levs]) for _, levs in sl]
    beta = np.array([JUMP_BETA[a] for a in ASSETS])
    rng_j = np.random.default_rng(seed + 7)

    # 初期状態
    Wj = [np.full(n, W0 * sh) for sh, _ in sl]
    gp_val = TODAY_W["GP"]
    Bj = [np.full(n, W0 * sh * (1 - gp_val * gp_gain0)) for sh, _ in sl]
    wcur = [np.tile(np.array([TODAY_W.get(a, 0.0) for a in ASSETS]), (n, 1)) for _ in sl]
    D = np.full(n, float(D0)); N = np.full(n, float(N0))
    pool = np.zeros((n, 4))       # 損失の繰越（当年, 1年前, 2年前, 3年前）
    lv = np.full(n, 1)            # 0遅れ 1予定どおり 2先行 3到達
    lam = np.ones(n)              # TIPP の比率（到達のときだけ使う）
    peak = np.full(n, H0); mindd = np.zeros(n); mindd60 = np.zeros(n); hit = np.zeros(n, bool)
    taxpaid = np.zeros(n); nswitch = np.zeros(n); lvl_months = np.zeros((n, 4))
    H60 = None; H60L = None; hit60 = None
    lam_rec = np.zeros(n)
    reached = np.zeros(n, bool)
    SN = None
    if snap:
        SN = dict(t=np.full(n, -1), Wb=np.zeros(n), Bb=np.zeros(n), pool=np.zeros(n), D=np.zeros(n), N=np.zeros(n),
                  tax=np.zeros(n), Wa=np.zeros(n), wold=np.zeros((n, len(ASSETS))), wnew=np.zeros((n, len(ASSETS))),
                  ret=np.zeros(n, bool), Ha=np.zeros(n))
    Hrec = np.zeros((n, months)) if record else None
    LVrec = np.zeros((n, months), int) if record else None
    for t in range(months):
        m = M[:, t]
        if t > 0 and t % 12 == 0:
            pool[:, 1:] = pool[:, :-1].copy(); pool[:, 0] = 0.0
        Wtot = sum(Wj)
        H = Wtot + D + N
        # ---- 濃さ（月初に判定）----
        if goal:
            if t < 60:
                req = H0 * (G / H0) ** (t / 60)
            else:
                base60 = np.where(H60 >= G, G, H60)
                req = np.where(H60 >= G, G, base60 * (G / np.maximum(base60, 1.0)) ** ((t - 60) / 24))
            F = H / req
            Hr = H
            if reach_liq:
                Hr = H - TAU * np.maximum(Wtot - sum(Bj) - pool.sum(1), 0.0)
            des = np.where(Hr >= G, 3, np.where(F < 0.85, 0, np.where(F > 1.15, 2, 1)))
            if use_tf:
                des = np.where((des == 0) & ~tf[m], 1, des)
            if tipp_only:
                des = np.where(des == 3, 3, 1)          # 濃さは2段だけ（ふだん＝K0、到達＝床つき）。1⇔3は1段とみなす
                new_lv = des
            else:
                new_lv = lv + np.clip(des - lv, -1, 1) if one_step else des
        else:
            new_lv = np.full(n, 1)
        nswitch += (new_lv != lv) & (t > 0)
        lv = new_lv
        if use_tipp:
            lam_new = np.clip((H - G - 0.25 * (D + N)) / np.maximum(0.25 * Wtot, 1.0), 0.0, 1.0)
            lam_new = np.floor(lam_new * 4 + 1e-9) / 4
            lam = np.where(lv == 3, lam_new, 1.0)
        lvl_months[np.arange(n), lv] += 1
        first_now = (lv == 3) & ~reached if snap else None
        # ---- 各スリーブ：売却（含み益の実現と税）→ 月次リターン ----
        jump_now = None
        if jump is not None:
            jump_now = rng_j.random(n) < jump["p"]
        for j in range(nsl):
            s_id = lev_ids[j][lv]                       # 使うシリーズ（経路ごと）
            if use_tipp and j == 0:
                s_id = np.where(lv == 3, sid[sl[j][1][1]], s_id)   # 到達は「予定どおり」×λ
                scale = np.where(lv == 3, lam, 1.0)
            else:
                scale = np.ones(n)
            wnew = WT[s_id, m] * scale[:, None]
            inv_old = wcur[j].sum(1)
            sold = np.maximum(wcur[j] - wnew, 0.0).sum(1)
            s = np.where(inv_old > 1e-12, sold / np.maximum(inv_old, 1e-12), 0.0)
            ftot = 1 - (1 - np.clip(s, 0, 1)) * (1 - Fr[s_id, m])
            g = ftot * (Wj[j] - Bj[j])
            # 損失の繰越を古い順に使う
            gp = np.maximum(g, 0.0)
            use_total = np.zeros(n)
            for b in (3, 2, 1, 0):
                u = np.minimum(pool[:, b], gp - use_total)
                pool[:, b] -= u; use_total += u
            tax = TAU * (gp - use_total) if tax_on else np.zeros(n)
            pool[:, 0] += np.maximum(-g, 0.0)
            if snap and j == 0:
                fm = first_now
                SN["t"][fm] = t; SN["Wb"][fm] = Wj[j][fm]; SN["Bb"][fm] = Bj[j][fm]; SN["pool"][fm] = pool.sum(1)[fm]
                SN["D"][fm] = D[fm]; SN["N"][fm] = N[fm]; SN["tax"][fm] = tax[fm]; SN["Wa"][fm] = (Wj[j] - tax)[fm]
                SN["wold"][fm] = wcur[j][fm]; SN["wnew"][fm] = wnew[fm]; SN["ret"][fm] = ret[m][fm]
            Wj[j] = Wj[j] - tax
            Bj[j] = Bj[j] + g - tax
            taxpaid += tax
            r = scale * R[s_id, m]
            if jump_now is not None:
                rj = (wnew * beta).sum(1) * jump["J"]
                if jump.get("total_loss"):
                    tq = wnew[:, ASSETS.index("TQQQ")]
                    rj = rj - tq * 3 * jump["J"] + tq * (-1.0)     # TQQQ部分は全損
                rj = np.maximum(rj, -1.0)
                r = np.where(jump_now, (1 + r) * (1 + rj) - 1, r)
            Wj[j] = Wj[j] * (1 + r)
            wcur[j] = wnew
        # DC・NISA
        dr = dc[m]; nr = nis[m]
        if jump_now is not None:
            dr = np.where(jump_now & ~ret[m], (1 + dr) * (1 + 0.75 * jump["J"]) - 1, dr)
            nr = np.where(jump_now, (1 + nr) * (1 + max(1.25 * jump["J"], -1.0)) - 1, nr)
        D = (D + cDC) * (1 + dr)
        N = (N + cN) * (1 + nr)
        Wtot = sum(Wj)
        H = Wtot + D + N
        if record:
            Hrec[:, t] = H; LVrec[:, t] = lv
        if snap:
            reached |= first_now
        peak = np.maximum(peak, H); dd = H / peak - 1
        mindd = np.minimum(mindd, dd)
        hit |= H >= G
        if t == 59:
            H60 = H.copy(); mindd60 = mindd.copy(); hit60 = hit.copy()
            lat = TAU * np.maximum(Wtot - sum(Bj) - pool.sum(1), 0.0)
            H60L = H - lat
    Wtot = sum(Wj)
    lat = TAU * np.maximum(Wtot - sum(Bj) - pool.sum(1), 0.0)
    out = dict(H=H, HL=H - lat, mindd=mindd, hit=hit, W=Wtot, D=D, N=N, tax=taxpaid, nswitch=nswitch,
               lvl=lvl_months / months, H60=H60, H60L=H60L, mindd60=mindd60, hit60=hit60, M=M, Hrec=Hrec, LVrec=LVrec, SN=SN)
    return out


def summarize(p, horizon=60):
    """経路 → 指標（物差し）"""
    if horizon == 60 or p["H60"] is None:
        H, HL, dd, hit = (p["H60"], p["H60L"], p["mindd60"], p["hit60"]) if p["H60"] is not None else (p["H"], p["HL"], p["mindd"], p["hit"])
    else:
        H, HL, dd, hit = p["H"], p["HL"], p["mindd"], p["hit"]
    ok = H >= G
    return {"1億以上": ok.mean(), "一度でも1億": hit.mean(), "中央値": np.median(H), "悪いほう10%": np.percentile(H, 10),
            "悪いほう5%": np.percentile(H, 5), "良いほう10%": np.percentile(H, 90),
            "1億以上の平均": H[ok].mean() if ok.any() else np.nan, "1.5億以上": (H >= 1.5e8).mean(),
            "元本割れ": (H < H0).mean(), "途中30超": (dd <= -0.30).mean(), "途中40超": (dd <= -0.40).mean(),
            "途中50超": (dd <= -0.50).mean(),
            "換金後1億以上": (HL >= G).mean(), "換金後元本割れ": (HL < H0).mean(), "換金後中央値": np.median(HL),
            "税の中央値": np.median(p["tax"])}


def paired_se(a, b):
    d = a.astype(float) - b.astype(float)
    return d.std(ddof=1) / math.sqrt(len(d))
