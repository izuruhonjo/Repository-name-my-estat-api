"""
世帯3口座（S2口座・DC・NISA）を同じ相場で同時に動かすエンジン
------------------------------------------------------------------
・DC：口座内のスイッチングは非課税。売却→約5営業日の待機→買付（スイッチングの待ち時間を再現）
・NISA：FANG+。口座内の売買は非課税だが、売った枠は翌年まで戻らない（年間枠・生涯枠を管理）
・S2口座：既存エンジン（s2engine.py）の月次リターンを使用。G5の目標到達ルールは「世帯合計」で判定
・モンテカルロは3口座の月次リターンを「同じ月」で12ヶ月ブロック抽出（口座間の相関を保つ）
"""
import math
import numpy as np, pandas as pd
import s2engine as E

# 価格データは配当なしの終値なので、配当・利息を年率で足す（概算）
YIELD = {"spy": 0.018, "efa": 0.028, "eem": 0.023, "ewj": 0.018, "qqq": 0.007,
         "ief": 0.030, "bwx": 0.015, "fngs": 0.0}
FEE = {"DEV": 0.0015, "JP": 0.0015, "EM": 0.0020, "FBOND": 0.0015, "NDX1": 0.0020, "FANG": 0.0078}
PRIN_RATE = 0.001       # 元本確保型（定期預金型）の利回り（年）
DBOND_RATE = 0.003      # 国内債券インデックス（年）
DC_CASH_DAYS = 5        # DCスイッチングで現金になっている営業日数


def load_all(data="data"):
    mkt = E.load_market(data)
    for nm, fn in [("spy", "SPY"), ("ewj", "EWJ"), ("efa", "EFA"), ("eem", "EEM"), ("bwx", "BWX"), ("fngs", "FNGS")]:
        try:
            mkt[nm] = E._load_csv(f"{data}/{fn}.csv").reindex(mkt.index, method="ffill")
        except FileNotFoundError:
            mkt[nm] = np.nan
    return mkt


def asset_returns(mkt):
    """円建て・配当込み・信託報酬控除の日次リターン。"""
    rfx = mkt["fx"].pct_change().fillna(0)
    def usd(col):
        r = mkt[col].pct_change()
        r = r.where(mkt[col].shift(1).notna())
        return r + YIELD.get(col, 0) / 252
    jpy = lambda r: (1 + r) * (1 + rfx) - 1
    A = pd.DataFrame(index=mkt.index)
    spy, efa = usd("spy"), usd("efa")
    # 先進国株（日本除く）≒ 米国72%＋その他先進国28%（EFAが無い2001-08以前は米国100%）
    dev_usd = (0.72 * spy + 0.28 * efa).where(efa.notna(), spy)
    A["DEV"] = jpy(dev_usd) - FEE["DEV"] / 252
    A["US"] = jpy(spy) - 0.001 / 252                     # 米国株（S&P500）インデックス
    A["JP"] = jpy(usd("ewj")) - FEE["JP"] / 252          # EWJ（ドル建て）×為替＝円建ての日本株
    em = usd("eem")
    A["EM"] = jpy(em.where(em.notna(), dev_usd)) - FEE["EM"] / 252   # 2003-04以前は先進国株で代用
    ief, bwx = usd("ief"), usd("bwx")
    fb = (0.5 * ief + 0.5 * bwx).where(bwx.notna(), ief)
    A["FBOND"] = jpy(fb.fillna(0.0)) - FEE["FBOND"] / 252  # 外国債券（2002-07以前は0）
    A["NDX1"] = jpy(usd("qqq")) - FEE["NDX1"] / 252
    fg = usd("fngs")
    A["FANG"] = jpy(fg.where(fg.notna(), usd("qqq"))) - FEE["FANG"] / 252   # FNGS以前はNASDAQ100で代用（控えめ）
    A["FANG_real"] = fg.notna()
    A["PRIN"] = PRIN_RATE / 252
    A["DBOND"] = DBOND_RATE / 252
    A["CASH"] = 0.0
    return A.fillna({"US": 0, "DEV": 0, "JP": 0, "EM": 0, "FBOND": 0, "NDX1": 0, "FANG": 0})


# ---------------------------------------------------------------
# DC戦略：月末に「次に持つもの」を決め、翌営業日に売却→5営業日現金→買付
# ---------------------------------------------------------------
def month_end_info(mkt, A, judg):
    me = E.month_end_dates(mkt.index)
    px = (1 + A[["US", "DEV", "JP", "EM", "FBOND", "NDX1", "FANG"]]).cumprod().loc[me]
    mom12 = px / px.shift(12) - 1
    sma10 = px > px.rolling(10).mean()
    st = judg["state"].reindex(me)
    return me, mom12, sma10, st


DC_RULES = {}
def dc_rule(name):
    def deco(f):
        DC_RULES[name] = f
        return f
    return deco

@dc_rule("D0 先進国株を持ちっぱなし")
def _d0(k, mom, sma, st):
    return "DEV"

@dc_rule("D1 DC④（○先進国株／×元本確保）")
def _d1(k, mom, sma, st):
    return "DEV" if st in ("NORMAL", "DIP") else "PRIN"

@dc_rule("D2 ○は株3種の12ヶ月勝者／×元本確保")
def _d2(k, mom, sma, st):
    if st not in ("NORMAL", "DIP"):
        return "PRIN"
    m = mom.iloc[k][["DEV", "JP", "EM"]].dropna()
    return m.idxmax() if len(m) else "DEV"

@dc_rule("D3 ○先進国株／×外国債券（債券が上昇トレンドのとき）")
def _d3(k, mom, sma, st):
    if st in ("NORMAL", "DIP"):
        return "DEV"
    return "FBOND" if mom.iloc[k]["FBOND"] > 0 else "PRIN"

@dc_rule("D4 先進国株の10ヶ月線（QQQの○×を使わない）")
def _d4(k, mom, sma, st):
    return "DEV" if sma.iloc[k]["DEV"] else "PRIN"

@dc_rule("D5 デュアル・モメンタム（株3種の勝者、負なら債券／元本）")
def _d5(k, mom, sma, st):
    m = mom.iloc[k][["DEV", "JP", "EM"]].dropna()
    if not len(m):
        return "DEV"
    best = m.idxmax()
    if m[best] > 0:
        return best
    return "FBOND" if mom.iloc[k]["FBOND"] > 0 else "PRIN"

@dc_rule("D6 ○NASDAQ100／×元本確保（品揃えにある場合）")
def _d6(k, mom, sma, st):
    return "NDX1" if st in ("NORMAL", "DIP") else "PRIN"

@dc_rule("D8 ○米国株S&P500／×元本確保（品揃えにある場合）")
def _d8(k, mom, sma, st):
    return "US" if st in ("NORMAL", "DIP") else "PRIN"

@dc_rule("D7 ○NASDAQ100（通常のみ）・押し目は先進国株／×元本確保")
def _d7(k, mom, sma, st):
    if st == "NORMAL":
        return "NDX1"
    return "DEV" if st == "DIP" else "PRIN"


def run_dc(mkt, A, judg, rule, start="2000-04-01", end="2026-10-31", cash_days=DC_CASH_DAYS, exec_lag=1):
    """拠出なし（時間加重）の日次NAVと、各営業日に持っている資産。"""
    idx = mkt.index
    me, mom, sma, st = month_end_info(mkt, A, judg)
    me_pos = {d: k for k, d in enumerate(me)}
    i0 = idx.searchsorted(pd.Timestamp(start)); i1 = idx.searchsorted(pd.Timestamp(end), side="right")
    k0 = max(k for k, d in enumerate(me) if d < idx[i0])
    cur = rule(k0, mom, sma, st.iloc[k0]) if not pd.isna(st.iloc[k0]) else "DEV"
    nav = np.zeros(i1 - i0); v = 1.0; hold = []
    sell_i = buy_i = None; tgt = None; n_sw = 0
    arr = {c: A[c].values for c in ["US", "DEV", "JP", "EM", "FBOND", "NDX1", "FANG", "PRIN", "CASH"]}
    for i in range(i0, i1):
        if sell_i is not None and i == sell_i:
            cur = "CASH"
        if buy_i is not None and i == buy_i:
            cur = tgt; sell_i = buy_i = None; n_sw += 1
        v *= 1 + arr[cur][i]
        nav[i - i0] = v
        hold.append(cur)
        d = idx[i]
        if d in me_pos and sell_i is None:
            k = me_pos[d]
            s = st.iloc[k]
            if pd.isna(s):
                continue
            t = rule(k, mom, sma, s)
            if t != cur:
                tgt = t
                if cur in ("PRIN", "CASH") and t == "PRIN":
                    cur = "PRIN"; continue
                sell_i = i + exec_lag
                buy_i = sell_i + cash_days
    return pd.Series(nav, index=idx[i0:i1]), pd.Series(hold, index=idx[i0:i1]), n_sw


def run_hold(A, col, start="2000-04-01", end="2026-10-31"):
    r = A[col][(A.index >= start) & (A.index <= end)]
    return (1 + r).cumprod()


def run_nisa_switch(mkt, A, judg, start="2000-04-01", end="2026-10-31"):
    """参考：NISA内でFANG+⇔国内債券を○×で切り替える（枠の制約は無視＝上限の見積り）。"""
    rule = lambda k, mom, sma, st: "FANG" if st in ("NORMAL", "DIP") else "DBOND"
    A2 = A.copy(); A2["PRIN"] = A["DBOND"]
    def r2(k, mom, sma, st):
        return "FANG" if st in ("NORMAL", "DIP") else "PRIN"
    return run_dc(mkt, A2, judg, r2, start, end, cash_days=4)


def monthly(nav):
    return nav.resample("ME").last().pct_change().dropna()


# ---------------------------------------------------------------
# 世帯モンテカルロ
# ---------------------------------------------------------------
def build_month_table(s2_nav, s2_states, dc_navs: dict, A, rate_daily=None):
    """同じ月で並べた月次表。"""
    T = pd.DataFrame({"S2": monthly(s2_nav)})
    for k, nv in dc_navs.items():
        T[k] = monthly(nv)
    for c in ["DEV", "FANG", "NDX1", "DBOND", "PRIN"]:
        T["A_" + c] = monthly((1 + A[c]).cumprod().loc[s2_nav.index])
    st = s2_states["state"].resample("ME").first()       # その月の初めの状態
    T["RET"] = (st.reindex(T.index) == "RETREAT").astype(float)
    T["RATE"] = rate_daily.resample("ME").mean().reindex(T.index) if rate_daily is not None else 0.035
    return T.dropna()


def hh_mc(T, dc_col, nisa_col="A_FANG", n=20000, seed=42, months=60, weights=None, block=12,
          W0=39_700_000, D0=9_000_000, N0=650_000, cS2=0, cDC=27_500, cN=50_000,
          goal=True, behind=2.5, ahead=1.2, reached=0.5, base_L=2.0, target=1e8,
          rate=0.035, lev_cost=0.03, nisa_from_s2_in_retreat=0.0, nisa_annual_spare=6_600_000,
          nisa_lifetime_spare=35_350_000, nisa_jan_fill=0.0, dc_contrib_to=None, start_idx=None, s2c_to_nisa_in_ret=False, lo=0.85, hi=1.15, return_paths=False):
    """
    dc_col: DC戦略の月次リターン列。dc_contrib_to: Noneなら掛金も同じ戦略、'A_DEV'なら×中も掛金は先進国株へ
    nisa_from_s2_in_retreat: ×の月にS2口座の何割を（年間の空き枠まで）NISAのFANG+へ移すか
    nisa_jan_fill: 毎年1月にS2口座の何割を空き枠までNISAへ移すか
    start_idx: Noneならブロック抽出、整数配列なら歴史の5年窓をそのまま使う（ローリング検証）
    """
    s2 = T["S2"].values; ret = T["RET"].values
    rate_m = T["RATE"].values if "RATE" in T else np.full(len(s2), rate)
    dc = T[dc_col].values; nis = T[nisa_col].values
    dcc = T[dc_contrib_to].values if dc_contrib_to else None
    TT = len(s2)
    rng = np.random.default_rng(seed)
    if start_idx is None:
        starts = np.arange(0, TT - block + 1)
        p = None if weights is None else np.asarray(weights)[:len(starts)] / np.asarray(weights)[:len(starts)].sum()
        nb = math.ceil(months / block)
        pick = rng.choice(starts, size=(n, nb), p=p)
        M = np.concatenate([pick[:, k][:, None] + np.arange(block) for k in range(nb)], axis=1)[:, :months]
    else:
        M = np.asarray(start_idx)[:, None] + np.arange(months)[None, :]
        n = M.shape[0]
    W = np.full(n, float(W0)); D = np.full(n, float(D0)); Dx = np.zeros(n); N = np.full(n, float(N0))
    H0 = W0 + D0 + N0
    peak = np.full(n, H0); mindd = np.zeros(n); hit = np.zeros(n, bool)
    quota = np.full(n, float(nisa_annual_spare)); life = np.full(n, float(nisa_lifetime_spare))
    moved = np.zeros(n)
    for t in range(months):
        m = M[:, t]
        if t % 12 == 0:
            quota[:] = nisa_annual_spare
            if nisa_jan_fill > 0:
                amt = np.minimum(np.minimum(quota, life), nisa_jan_fill * W)
                W -= amt; N += amt; quota -= amt; life -= amt; moved += amt
        H = W + D + Dx + N
        is_ret = ret[m] > 0.5
        # ×の月：S2の待機資金を空き枠までNISAへ
        if nisa_from_s2_in_retreat > 0:
            amt = np.where(is_ret, np.minimum(np.minimum(quota, life), nisa_from_s2_in_retreat * W), 0.0)
            W -= amt; N += amt; quota -= amt; life -= amt; moved += amt
        # S2の濃さ（世帯の到達度で判定、○の月だけ）
        req = H0 * (target / H0) ** (t / months)
        F = H / req
        if goal:
            L = np.where(F < lo, behind, np.where(F > hi, ahead, base_L))
            L = np.where(H >= target, reached, L)
        else:
            L = np.full(n, base_L)
        # S2の月次リターンには「ゴールドプラス＝2倍」の金利コストが既に入っている。
        # 濃さLのときの正しい金利負担は (L-1)×金利 なので、差分 (L-1-L/2)×金利 だけを調整する（L=2なら調整ゼロ）。
        # TQQQ部分（Lが2超）にだけ追加コスト lev_cost を足す。
        rt = rate_m[m]
        r_on = (L / 2.0) * s2[m] - (np.maximum(L - 1, 0) - L / 2.0) * rt / 12 - np.maximum(L - 2, 0) * lev_cost / 12
        r_s2 = np.where(is_ret, s2[m], r_on)
        c_s2 = np.where(is_ret & s2c_to_nisa_in_ret, 0.0, cS2)      # ×の月はS2の積立をNISAへ回す案
        c_n = cN + (cS2 - c_s2)
        W = (W + c_s2) * (1 + r_s2)
        # DC
        if dcc is None:
            D = (D + cDC) * (1 + dc[m])
        else:
            # ×中の掛金は別の箱（先進国株）に入れ、○に戻ったら本体へ合流
            Dx = np.where(is_ret, (Dx + cDC) * (1 + dcc[m]), 0.0)
            D = np.where(is_ret, D * (1 + dc[m]), (D + cDC) * (1 + dc[m]))
        # NISA（毎月の積立は年間枠の内側：空き枠は積立分を除いた値で渡す）
        N = (N + c_n) * (1 + nis[m])
        H = W + D + Dx + N
        peak = np.maximum(peak, H); mindd = np.minimum(mindd, H / peak - 1); hit |= H >= target
        if dcc is not None:
            # 翌月が○なら別の箱を本体へ合流
            nxt = ret[M[:, t + 1]] > 0.5 if t + 1 < months else np.zeros(n, bool)
            D = np.where(~nxt, D + Dx, D); Dx = np.where(~nxt, 0.0, Dx)
    H = W + D + Dx + N
    if return_paths:
        return dict(W=W, D=D + Dx, N=N, H=H, hit=hit, mindd=mindd)
    return dict(p_hit=hit.mean(), median=np.median(H), p10=np.percentile(H, 10), p90=np.percentile(H, 90),
                p_dd30=(mindd <= -0.30).mean(), p_dd50=(mindd <= -0.50).mean(),
                med_S2=np.median(W), med_DC=np.median(D + Dx), med_NISA=np.median(N), med_moved=np.median(moved),
                p_final=(H >= target).mean())
