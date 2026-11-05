"""
G5：5年で1億を狙う0ベース戦略（ゴール型・多資産トレンド・ボラ目標・資金到達度でレバ調整）
  理論的土台：Moskowitz-Ooi-Pedersen(2012) 時系列モメンタム、Faber(2007) 10ヶ月線、
  Moreira-Muir(2017) ボラ管理、Qian(2005) リスクパリティ、Browne(1999) 期限付き目標到達の最適戦略、
  Black-Perold(1992) CPPI（床）、Merton(1969) 動的配分。
"""
import sys, math, itertools
import numpy as np, pandas as pd
sys.path.insert(0, ".")
import s2engine as E

ASSETS = {  # 名前: (列, 円換算するか, 年コスト)
    "QQQ": ("qqq", True, 0.002), "SPY": ("spy", True, 0.001), "SMH": ("smh", True, 0.0035),
    "GOLD": ("gold", True, 0.004), "JP": ("n225", False, 0.001), "TLT": ("tlt", True, 0.0015),
}
LEV_COST = 0.010   # 2倍ファンドの追加コスト（年）
TAX = 0.20315


def load(data_dir="data"):
    mkt = E.load_market(data_dir)
    for nm, fn in [("spy", "SPY"), ("n225", "N225ETF"), ("ewj", "EWJ"), ("btc", "BTCUSD")]:
        try:
            s = E._load_csv(f"{data_dir}/{fn}.csv"); mkt[nm] = s.reindex(mkt.index, method="ffill")
        except FileNotFoundError:
            mkt[nm] = np.nan
    if mkt["n225"].isna().all():            # 日本株ETFが無ければEWJ（ドル建て→円）で代替
        mkt["n225"] = mkt["ewj"] * mkt["fx"]
        ASSETS["JP"] = ("n225", False, 0.005)
    return mkt


def jpy_returns(mkt):
    rfx = mkt["fx"].pct_change().fillna(0)
    R = pd.DataFrame(index=mkt.index)
    for k, (col, conv, fee) in ASSETS.items():
        r = mkt[col].pct_change()
        if conv:
            r = (1 + r) * (1 + rfx) - 1
        R[k] = r - fee / 252
    return R


def backtest(mkt, R, vol_target=0.20, lmax=1.5, mom_m=12, sma_m=10, vol_win=60, weighting='inv',
             start="2000-04-01", end="2026-10-31", tax=TAX, nisa_share_fn=None, cost=0.001,
             goal=None):
    """月末に判定・翌営業日に執行。goal=(W0, target, months) で資金到達度に応じて lmax を調整。"""
    idx = R.index
    me = E.month_end_dates(idx)
    px = (1 + R.fillna(0)).cumprod()
    rate = mkt["rate"]
    i0 = idx.searchsorted(pd.Timestamp(start)); i1 = idx.searchsorted(pd.Timestamp(end), side="right")
    w = pd.Series(0.0, index=R.columns)
    nav = 1.0; navs = np.zeros(i1 - i0); lev_hist = []; w_hist = []
    cost_basis = 1.0; loss_carry = 0.0; taxes = 0.0
    me_set = set(me)
    pending_w = None
    peak = 1.0
    for i in range(i0, i1):
        d = idx[i]
        if pending_w is not None:
            # 執行：売買コストと税（利益部分の売却に課税、NISA分は非課税）
            turnover = (pending_w - w).abs().sum()
            nav *= (1 - cost * turnover)
            sold_frac = (w - pending_w).clip(lower=0).sum() / max(w.sum(), 1e-9) if w.sum() > 0 else 0
            if sold_frac > 0 and tax > 0:
                gain = (nav - cost_basis) * sold_frac
                nisa = nisa_share_fn(d) if nisa_share_fn else 0.0
                if gain > 0:
                    taxable = max(0.0, gain - loss_carry); loss_carry = max(0.0, loss_carry - gain)
                    t = taxable * tax * (1 - nisa); nav -= t; taxes += t
                else:
                    loss_carry += -gain
                cost_basis = cost_basis + (nav - cost_basis) * sold_frac  # 売った分の簿価を更新
            w = pending_w; pending_w = None
        # 日次リターン
        r = R.iloc[i].fillna(0.0)
        gross = (w * r).sum()
        L = w.sum()
        fin = max(0.0, L - 1) * (rate.iloc[i] + LEV_COST) / 252
        nav *= (1 + gross - fin)
        navs[i - i0] = nav
        peak = max(peak, nav)
        # 月末判定
        if d in me_set:
            k = me.get_loc(d)
            if k < mom_m:
                continue
            p = px.loc[me]
            mom = p.iloc[k] / p.iloc[k - mom_m] - 1
            sma = px.loc[d] > p.iloc[k - sma_m + 1:k + 1].mean()
            on = (mom > 0) & sma
            vol = R.iloc[i - vol_win + 1:i + 1].std() * math.sqrt(252)
            if weighting == 'inv':
                inv = (1 / vol).where(on, 0.0).fillna(0.0)
            elif weighting == 'eq':
                inv = on.astype(float)
            else:  # mom：12ヶ月モメンタムをボラで割った強さに比例
                inv = (mom / vol).clip(lower=0).where(on, 0.0).fillna(0.0)
            if inv.sum() == 0:
                tw = pd.Series(0.0, index=R.columns)
            else:
                base_w = inv / inv.sum()
                cov = R.iloc[i - vol_win + 1:i + 1].cov() * 252
                pvol = math.sqrt(max(base_w @ cov @ base_w, 1e-12))
                lm = lmax
                if goal is not None:
                    W0, target, months = goal
                    t = (d.year - pd.Timestamp(start).year) * 12 + d.month - pd.Timestamp(start).month
                    t_in = t % months
                    if t_in == 0 and t > 0:
                        pass
                    req = (target / W0) ** (t_in / months)
                    # 窓の起点を5年ごとにリセット
                    win_start_i = idx.searchsorted(pd.Timestamp(start) + pd.DateOffset(months=t - t_in))
                    w_start = navs[win_start_i - i0] if win_start_i - i0 >= 0 and win_start_i - i0 < len(navs) and navs[win_start_i - i0] > 0 else 1.0
                    F = (nav / w_start) / req
                    lm = lmax * (1.3 if F < 0.85 else 0.6 if F > 1.15 else 1.0)
                    if nav / peak < 0.70:        # 床：高値から30%下は半分に
                        lm = min(lm, 0.5 * lmax)
                scale = min(vol_target / pvol, lm)
                tw = base_w * scale
            pending_w = tw
            lev_hist.append((d, tw.sum())); w_hist.append((d, *tw.values))
    nav_s = pd.Series(navs, index=idx[i0:i1])
    return nav_s, pd.DataFrame(w_hist, columns=["date", *R.columns]).set_index("date"), taxes


def mc_goal(mr_unlev: pd.Series, W0=39_700_000, target=100_000_000, months=60, n=20000, seed=42,
            lmax=1.5, rate=0.035, lev_cost=0.01, goal_rule=True, floor_dd=0.30, contrib=0.0,
            other0=0.0, other_g=0.06, weights=None):
    """月次のレバ1倍リターンを12ヶ月ブロックで引き直し、レバ調整ルールを経路ごとに適用。"""
    rng = np.random.default_rng(seed)
    r = mr_unlev.values; T = len(r); block = 12
    starts = np.arange(0, T - block + 1)
    p = None if weights is None else np.asarray(weights)[:len(starts)] / np.asarray(weights)[:len(starts)].sum()
    nb = math.ceil(months / block)
    pick = rng.choice(starts, size=(n, nb), p=p)
    paths = np.concatenate([r[pick[:, k][:, None] + np.arange(block)] for k in range(nb)], axis=1)[:, :months]
    W = np.full(n, float(W0)); peak = W.copy(); hit = np.zeros(n, bool); mindd = np.zeros(n)
    other = np.full(n, float(other0))
    for t in range(months):
        req = W0 * (target / W0) ** (t / months)
        F = W / req
        L = np.full(n, lmax)
        if goal_rule:
            L = np.where(F < 0.85, lmax * 1.3, np.where(F > 1.15, lmax * 0.6, lmax))
            L = np.where(W / peak < 1 - floor_dd, np.minimum(L, 0.5 * lmax), L)
            L = np.where(W + other >= target, 0.5, L)      # 到達後は守る
        rl = L * paths[:, t] - np.maximum(L - 1, 0) * (rate + lev_cost) / 12
        W = W * (1 + rl) + contrib
        other = other * (1 + other_g / 12)
        peak = np.maximum(peak, W)
        mindd = np.minimum(mindd, W / peak - 1)
        hit |= (W + other) >= target
    return dict(p_hit=hit.mean(), median=np.median(W + other), p10=np.percentile(W + other, 10),
                p_dd30=(mindd <= -0.30).mean(), p_dd50=(mindd <= -0.50).mean(), median_W=np.median(W))
