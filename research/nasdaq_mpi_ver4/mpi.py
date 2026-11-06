"""月足MACD&パラボリック投資法 ver.4.0 再現・コスト検証エンジン

ケース
  A : 記事条件の再現（日次騰落率×L の疑似レバ、コストなし、売却ごと利益に20.315%、月末終値約定、円ドル無視）
  B : A + ファンド内コスト（借入/スワップ・経費率を実TQQQで較正）+ 1倍の配当 + 翌営業日約定
  C : B + SBI手数料(0.495%,上限22USD) + スリッページ + 為替(円建て投資家) + 日本の税制
      (特定口座・年内損益通算・3年繰越・配当は米10%+国内20.315%)
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
TAX = 0.20315
DIV_TAX = 1 - (1 - 0.10) * (1 - TAX)  # 米源泉10% + 国内20.315% (外国税額控除なし) = 28.28%


# ----------------------------------------------------------------- data
def load_yahoo(sym: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{sym}_daily.csv", index_col=0, parse_dates=True)
    return df[~df.index.duplicated(keep="last")].sort_index()


def load_fred(sid: str) -> pd.Series:
    d = pd.read_csv(DATA / f"{sid}.csv")
    d.columns = ["date", sid]
    d["date"] = pd.to_datetime(d["date"])
    s = pd.to_numeric(d[sid], errors="coerce")
    return pd.Series(s.values, index=d["date"]).ffill()


def build_daily() -> pd.DataFrame:
    ndx = load_yahoo("NDX")
    qqq = load_yahoo("QQQ")
    idx = ndx.index
    df = pd.DataFrame(index=idx)
    df["o"], df["h"], df["l"], df["c"] = ndx.o, ndx.h, ndx.l, ndx.c
    df["r"] = df.c.pct_change().fillna(0.0)
    df["dt"] = df.index.to_series().diff().dt.days.fillna(1).astype(float)  # 暦日数
    df["rf"] = load_fred("DTB3").reindex(idx, method="ffill").values / 100.0
    df["fx"] = load_fred("DEXJPUS").reindex(idx, method="ffill").values
    # 1倍の日次配当利回り: QQQ の adj/close 比の変化から抽出。1999/3以前は年0.4%と仮定
    q = qqq.reindex(idx)
    ratio = (q.adj / q.c)
    d = (ratio / ratio.shift(1) - 1).clip(lower=0).fillna(0.0)
    d[idx < qqq.index[0] + pd.Timedelta(days=1)] = 0.004 / 252
    df["dy"] = d.values
    return df


# ------------------------------------------------------------ indicators (Pine v4 準拠)
def pine_ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    a = 2.0 / (n + 1)
    valid = ~np.isnan(x)
    if valid.sum() < n:
        return out
    first = np.argmax(valid)
    seed = first + n - 1
    out[seed] = np.mean(x[first:seed + 1])
    for i in range(seed + 1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def pine_sar(h, l, c, start, inc, mx) -> np.ndarray:
    """TradingView ta.sar のリファレンス実装を移植"""
    n = len(c)
    res = np.full(n, np.nan)
    result = maxmin = acc = np.nan
    below = None
    for i in range(1, n):
        first_trend = False
        if i == 1:
            if c[1] > c[0]:
                below, maxmin, result = True, h[1], l[0]
            else:
                below, maxmin, result = False, l[1], h[0]
            first_trend, acc = True, start
        result = result + acc * (maxmin - result)
        if below:
            if result > l[i]:
                first_trend, below = True, False
                result = max(h[i], maxmin)
                maxmin, acc = l[i], start
        else:
            if result < h[i]:
                first_trend, below = True, True
                result = min(l[i], maxmin)
                maxmin, acc = h[i], start
        if not first_trend:
            if below:
                if h[i] > maxmin:
                    maxmin, acc = h[i], min(acc + inc, mx)
            else:
                if l[i] < maxmin:
                    maxmin, acc = l[i], min(acc + inc, mx)
        if below:
            result = min(result, l[i - 1])
            if i > 1:
                result = min(result, l[i - 2])
        else:
            result = max(result, h[i - 1])
            if i > 1:
                result = max(result, h[i - 2])
        res[i] = result
    return res


def monthly_bars(daily: pd.DataFrame) -> pd.DataFrame:
    g = daily.groupby(daily.index.to_period("M"))
    m = pd.DataFrame({"o": g.o.first(), "h": g.h.max(), "l": g.l.min(), "c": g.c.last(),
                      "last_day": g.apply(lambda x: x.index[-1])})
    return m


def signals(m: pd.DataFrame, fast=12, slow=26, sig=9, ps=(0.02, 0.02, 0.2)) -> pd.DataFrame:
    """記事掲載の Pine Script (MPI) の条件をそのまま移植。+1=買(Long) / -1=売(Profit)"""
    h, l, c = m.h.values, m.l.values, m.c.values
    macd = pine_ema(c, fast) - pine_ema(c, slow)
    signal = pine_ema(macd, sig)
    psar = pine_sar(h, l, c, *ps)
    n = len(c)
    out = np.zeros(n, dtype=int)
    long_sing, profit_sing = 1, 1
    for i in range(1, n):
        if np.isnan(signal[i]) or np.isnan(signal[i - 1]) or np.isnan(psar[i - 1]):
            continue
        xo = macd[i] > signal[i] and macd[i - 1] <= signal[i - 1]
        xu = macd[i] < signal[i] and macd[i - 1] >= signal[i - 1]
        long_c = (l[i] > psar[i] and xo) or (macd[i] > signal[i] and h[i - 1] < psar[i - 1] and h[i] > psar[i])
        prof_c = (h[i] < psar[i] and xu) or (macd[i] < signal[i] and l[i - 1] > psar[i - 1] and l[i] < psar[i])
        if long_sing and long_c:
            long_sing, profit_sing, out[i] = 0, 1, 1
        if profit_sing and prof_c:          # Pine と同じ順序で評価
            profit_sing, long_sing, out[i] = 0, 1, -1
    r = m.copy()
    r["macd"], r["signal"], r["psar"], r["sig"] = macd, signal, psar, out
    return r


# ------------------------------------------------------------ synthetic assets
def lev_returns(daily: pd.DataFrame, L: float, cost: float, financing: bool) -> np.ndarray:
    """日次: L*r - (L-1)*rf*dt/365 - cost*dt/365  (cost = 経費率+スワップスプレッド等の総合)"""
    yr = daily.dt.values / 365.0
    if financing:  # 現実: スワップは配当込み指数に連動、(L-1)倍を短期金利で調達
        r = (daily.r.values + daily.dy.values) * L - (L - 1) * daily.rf.values * yr
    else:          # 記事: 価格指数の日次騰落率×L
        r = daily.r.values * L
    return r - cost * yr


def calibrate_cost(daily: pd.DataFrame, sym: str, L: float) -> tuple[float, dict]:
    act = load_yahoo(sym)
    s, e = act.index[0], act.index[-1]
    d = daily.loc[s:e]
    target = np.log(act.adj.iloc[-1] / act.adj.iloc[0])
    lo, hi = -0.05, 0.10
    for _ in range(80):
        mid = (lo + hi) / 2
        g = np.log1p(lev_returns(d, L, mid, True)[1:]).sum()
        lo, hi = (mid, hi) if g > target else (lo, mid)
    cost = (lo + hi) / 2
    syn = np.cumprod(1 + lev_returns(d, L, cost, True))
    syn = syn / syn[0]
    a = (act.adj / act.adj.iloc[0]).reindex(d.index).ffill().values
    te = np.std(np.diff(np.log(syn)) - np.diff(np.log(a))) * np.sqrt(252)
    nocost = np.cumprod(1 + lev_returns(d, L, 0.0, False))
    yrs = (e - s).days / 365.25
    info = dict(sym=sym, start=str(s.date()), end=str(e.date()), cost=cost, tracking_err=te,
                actual_cagr=(a[-1]) ** (1 / yrs) - 1, syn_cagr=syn[-1] ** (1 / yrs) - 1,
                article_cagr=(nocost[-1] / nocost[0]) ** (1 / yrs) - 1, years=yrs)
    return cost, info


# ------------------------------------------------------------ engine
@dataclass
class Cfg:
    name: str
    lev_cost: float = 0.0          # 3倍の総合コスト(年率、較正値) ※financing=True時は金利控除も
    financing: bool = False
    one_er: float = 0.0            # 1倍(QQQM) 経費率
    dividends: bool = False        # 1倍で配当を受取るか
    div_tax: bool = False
    exec_lag: int = 0              # 0=シグナル月の月末終値, 1=翌営業日終値
    contrib_at_month_end: bool = True
    commission: float = 0.0        # 0.495%
    comm_cap_usd: float = 1e18     # 22USD
    slippage: float = 0.0          # 片道
    fx: bool = False               # 円建て投資家として為替を反映
    fx_fee_yen: float = 0.0        # 円→ドル 1USDあたり(円)
    jp_tax: bool = False           # True: 年内通算+繰越3年 / False: 売却ごと利益に課税(記事)
    tax_on: bool = True
    infl_adj: bool = True          # 物価調整3万円(記事) / False: 名目3万円
    strategy: str = "mpi"          # mpi / dca1 / dca3
    transfer_pct: float = 0.01
    ps: tuple = (0.02, 0.02, 0.2)
    macd: tuple = (12, 26, 9)
    start: str = "1985-10"
    end: str = "2022-08"
    liquidate_tax: bool = True     # 最終時点で清算した場合の税引後も計算
    # 金利ルール（None なら常に3倍＝従来と同一）: 前営業日の米3M金利 > rate_thr なら2倍(lev_lo)を保有
    rate_thr: float | None = None
    rate_mode: str = "entry"       # entry=買シグナル時だけ判定 / monthly=積立日ごとに再判定し必要なら乗換
    lev_lo: float = 2.0
    lev_cost_lo: float = 0.0       # 2倍の総合コスト(年率、較正値)
    # 一括投資（既定0＝従来と同一）: 初日に initial 円を投入。monthly=None なら従来の積立額、0 なら積立なし
    initial: float = 0.0
    monthly: float | None = None
    init_regime: str | None = None  # "long"/"out": 開始時点の状態（開始前のシグナル履歴から決める場合に指定）


def contrib_amount(period: pd.Period, infl_adj: bool) -> float:
    if not infl_adj:
        return 30000.0
    k = (pd.Period("2022-08", "M") - period).n
    return 30000.0 * (11035.0 / 30000.0) ** (k / 442.0)


class Lot:
    """移動平均法の取得単価管理（円）"""
    def __init__(self):
        self.units = 0.0
        self.cost = 0.0  # 円(またはA/Bでは通貨単位)

    def buy(self, units, cost):
        self.units += units
        self.cost += cost

    def sell_all(self):
        u, c = self.units, self.cost
        self.units, self.cost = 0.0, 0.0
        return u, c


def run(daily: pd.DataFrame, sig: pd.DataFrame, cfg: Cfg, exec_dates=None):
    d = daily.loc[cfg.start: (pd.Period(cfg.end, "M") + 1).start_time - pd.Timedelta(days=1)].copy()
    r3 = lev_returns(d, 3.0, cfg.lev_cost, cfg.financing)
    r1 = d.r.values - cfg.one_er * d.dt.values / 365.0
    p3 = np.cumprod(1 + r3); p1 = np.cumprod(1 + r1)
    p3 /= p3[0]; p1 /= p1[0]
    if cfg.rate_thr is not None:
        p2 = np.cumprod(1 + lev_returns(d, cfg.lev_lo, cfg.lev_cost_lo, cfg.financing)); p2 /= p2[0]
    else:
        p2 = p3
    assert (1 + r3 > 0).all(), "3倍の日次リターンが-100%以下（全損）"
    rf_prev = np.r_[d.rf.values[0], d.rf.values[:-1]]   # 判定に使う金利は前営業日値（先読みなし）
    fx = d.fx.values if cfg.fx else np.ones(len(d))
    divs = d.dy.values if cfg.dividends else np.zeros(len(d))
    dates = d.index
    per = dates.to_period("M")
    is_first = np.r_[True, per[1:] != per[:-1]]
    is_last = np.r_[per[1:] != per[:-1], True]

    # シグナル → 執行日
    sig = sig.loc[cfg.start:cfg.end]
    exec_map = {}
    if exec_dates is not None:
        for dte, sg in exec_dates.items():
            pos = dates.searchsorted(dte)
            if pos < len(dates) and dates[pos] == dte and pos + cfg.exec_lag < len(dates):
                exec_map[pos + cfg.exec_lag] = sg
    for pm, row in (sig.iterrows() if exec_dates is None else []):
        if row.sig == 0:
            continue
        last = row.last_day
        pos = dates.searchsorted(last)
        if pos >= len(dates) or dates[pos] != last:
            continue
        ex = pos + cfg.exec_lag
        if ex < len(dates):
            exec_map[ex] = int(row.sig)

    L3, L2, L1 = Lot(), Lot(), Lot()
    cur = [3]                  # 保有中のレバ倍率（3 or 2）

    def want_lev(i):
        return 2 if (cfg.rate_thr is not None and rf_prev[i] > cfg.rate_thr) else 3

    def LX():
        return L3 if cur[0] == 3 else L2

    def pX(i):
        return p3[i] if cur[0] == 3 else p2[i]
    cash = 0.0                 # USD(またはA/Bでは通貨単位)
    cash_cost = 0.0            # 現金の円換算取得額（C: 為替差損益は現金保有中は非課税扱い→簡略化で無視）
    regime = "out"             # 最初の買シグナルまでは1倍へ積立
    if cfg.strategy == "dca3":
        regime = "long"
    if cfg.strategy == "mpi" and cfg.init_regime is not None:
        regime = cfg.init_regime
    transfer_amt = 0.0
    ytd_gain, ytd_withheld = 0.0, 0.0
    cf = []                    # [(year, loss)]
    cur_year = dates[0].year
    tax_paid_total = fees_total = fxfee_total = divtax_total = 0.0
    contrib_total = 0.0
    trades = []
    taxlog = []
    rows = []
    twr = 1.0
    prev_val = 0.0

    def fee(amount_usd):
        f = min(amount_usd * cfg.commission, cfg.comm_cap_usd) + amount_usd * cfg.slippage
        return f

    def realize(proceeds_yen, cost_yen, i):
        nonlocal ytd_gain, ytd_withheld, cash, tax_paid_total
        g = proceeds_yen - cost_yen
        if not cfg.tax_on:
            return 0.0
        if cfg.jp_tax:
            ytd_gain += g
            new_w = TAX * max(0.0, ytd_gain)
            t = new_w - ytd_withheld      # 負なら還付(源泉徴収ありの年内自動通算)
            ytd_withheld = new_w
        else:
            t = TAX * max(0.0, g)
        tax_paid_total += t
        return t

    def year_end(i_year):
        """確定申告で繰越控除適用 → 還付(年末で精算と簡略化)"""
        nonlocal ytd_gain, ytd_withheld, cf, cash, tax_paid_total
        if not (cfg.jp_tax and cfg.tax_on):
            return 0.0
        cf = [(y, a) for (y, a) in cf if i_year - y <= 3]
        refund = 0.0
        if ytd_gain > 0:
            use_total = 0.0
            newcf = []
            remain = ytd_gain
            for (y, a) in sorted(cf):
                u = min(a, remain)
                remain -= u; use_total += u
                if a - u > 1e-9:
                    newcf.append((y, a - u))
            cf = newcf
            refund = TAX * use_total
        elif ytd_gain < 0:
            cf.append((i_year, -ytd_gain))
        tax_paid_total -= refund
        taxlog.append(dict(year=i_year, realized_gain=ytd_gain, withheld=ytd_withheld,
                           cf_used=refund / TAX, refund=refund, cf_left=sum(a for _, a in cf)))
        ytd_gain, ytd_withheld = 0.0, 0.0
        return refund

    for i in range(len(d)):
        if dates[i].year != cur_year:
            refund_yen = year_end(cur_year)
            cash += refund_yen / fx[i]
            cur_year = dates[i].year
        val_before_flows = L3.units * p3[i] + L2.units * p2[i] + L1.units * p1[i] + cash
        if prev_val > 0:
            twr *= val_before_flows / prev_val
        # 1倍の配当
        if divs[i] > 0 and L1.units > 0:
            dv = L1.units * p1[i] * divs[i]
            net = dv * (1 - DIV_TAX) if cfg.div_tax else dv
            divtax_total += (dv - net) * fx[i]
            L1.buy(net / p1[i], net * fx[i])
        # シグナル執行
        if cfg.strategy == "mpi" and i in exec_map:
            s = exec_map[i]
            if s == -1 and regime == "long":
                gross = LX().units * pX(i)
                u, cst = LX().sell_all()
                f = fee(gross); fees_total += f * fx[i]
                net = gross - f
                t = realize(net * fx[i], cst, i)
                cash += net - t / fx[i]
                transfer_amt = cash * cfg.transfer_pct
                regime = "out"
                trades.append((dates[i], "SELL3", gross * fx[i], (net * fx[i] - cst)))
            elif s == 1 and regime == "out":
                u, cst = L1.sell_all()
                if u > 0:
                    gross = u * p1[i]
                    f = fee(gross); fees_total += f * fx[i]
                    net = gross - f
                    t = realize(net * fx[i], cst, i)
                    cash += net - t / fx[i]
                    trades.append((dates[i], "SELL1", gross * fx[i], (net * fx[i] - cst)))
                amt = cash
                cur[0] = want_lev(i)
                if amt > 0:
                    f = fee(amt); fees_total += f * fx[i]
                    LX().buy((amt - f) / pX(i), amt * fx[i])
                    cash = 0.0
                regime = "long"
                trades.append((dates[i], "BUY3", amt * fx[i], 0.0))
        # 毎月積立
        regular = is_last[i] if cfg.contrib_at_month_end else is_first[i]
        cday = regular or (i == 0 and cfg.initial > 0)
        flows = 0.0
        if (regular and cfg.strategy == "mpi" and regime == "long" and cfg.rate_mode == "monthly"
                and want_lev(i) != cur[0] and LX().units > 0):
            gross = LX().units * pX(i)
            u, cst = LX().sell_all()
            f = fee(gross); fees_total += f * fx[i]
            net = gross - f
            t = realize(net * fx[i], cst, i)
            amt = net - t / fx[i] + cash; cash = 0.0
            trades.append((dates[i], f"SWITCH{cur[0]}", gross * fx[i], (net * fx[i] - cst)))
            cur[0] = want_lev(i)
            f = fee(amt); fees_total += f * fx[i]
            LX().buy((amt - f) / pX(i), amt * fx[i])
        if cday:
            yen = ((contrib_amount(per[i], cfg.infl_adj) if cfg.monthly is None else cfg.monthly) if regular else 0.0) \
                + (cfg.initial if i == 0 else 0.0)
            contrib_total += yen
            rate = fx[i] + (cfg.fx_fee_yen if cfg.fx else 0.0)
            usd = yen / rate
            fxfee_total += yen - usd * fx[i]
            flows += usd
            f = fee(usd); fees_total += f * fx[i]
            tgt = LX() if (regime == "long" or cfg.strategy == "dca3") else L1
            if cfg.strategy == "dca1":
                tgt = L1
            px = p1[i] if tgt is L1 else pX(i)
            tgt.buy((usd - f) / px, yen)
            # 売シグナル中: 売却資金の1%を毎月1倍へ
            if cfg.strategy == "mpi" and regime == "out" and cash > 0:
                amt = min(transfer_amt, cash)
                f = fee(amt); fees_total += f * fx[i]
                L1.buy((amt - f) / p1[i], amt * fx[i])
                cash -= amt
        val = L3.units * p3[i] + L2.units * p2[i] + L1.units * p1[i] + cash
        prev_val = val
        rows.append((dates[i], val * fx[i], val, regime + ("2" if (regime == "long" and cur[0] == 2) else ""), contrib_total, twr))
        if prev_val > 0 and flows > 0:
            pass

    hist = pd.DataFrame(rows, columns=["date", "value_jpy", "value_ccy", "regime", "contrib", "twr"]).set_index("date")
    # 最終清算税
    i = len(d) - 1
    unreal = (L3.units * p3[i] * fx[i] - L3.cost) + (L2.units * p2[i] * fx[i] - L2.cost) + (L1.units * p1[i] * fx[i] - L1.cost)
    if cfg.jp_tax:
        g = ytd_gain + unreal
        avail = sum(a for (y, a) in cf if dates[i].year - y <= 3)
        liq_tax = TAX * max(0.0, g - avail) - ytd_withheld
    else:
        liq_tax = TAX * (max(0.0, L3.units * p3[i] * fx[i] - L3.cost) + max(0.0, L2.units * p2[i] * fx[i] - L2.cost)
                         + max(0.0, L1.units * p1[i] * fx[i] - L1.cost))
    if not cfg.tax_on:
        liq_tax = 0.0
    final = hist.value_jpy.iloc[-1]
    res = dict(case=cfg.name, end=str(dates[-1].date()), contrib=contrib_total, final_pre_liq=final,
               final_after_liq=final - liq_tax, tax_paid=tax_paid_total, fees=fees_total,
               fx_fees=fxfee_total, div_tax=divtax_total, n_trades=sum(1 for t in trades if t[1] != "BUY3"),
               n_switch=sum(1 for t in trades if t[1].startswith("SWITCH")),
               share_2x=float(np.mean([r[3] == "long2" for r in rows])) if rows else 0.0,
               mdd_twr=float((hist.twr / hist.twr.cummax() - 1).min()),
               mdd_value=float((hist.value_jpy / hist.value_jpy.cummax() - 1).min()))
    res["taxlog"] = taxlog
    res["irr"] = irr_monthly(hist, contrib_amount, cfg, final - liq_tax)
    return res, hist, trades


def irr_monthly(hist, fn, cfg, final):
    per = hist.index.to_period("M").unique()
    cfs = np.array([-(fn(p, cfg.infl_adj) if cfg.monthly is None else cfg.monthly) for p in per] + [final])
    cfs[0] -= cfg.initial
    def npv(r):
        t = np.arange(len(cfs)); t[-1] = len(cfs) - 2  # 最終値は最終月末
        return np.sum(cfs / (1 + r) ** t)
    lo, hi = -0.05, 0.2
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if npv(mid) > 0 else (lo, mid)
    return (1 + (lo + hi) / 2) ** 12 - 1


# ------------------------------------------------------------ 月中アラート約定（TradingView alert "Once per bar" 相当）
def _sar_step(state, i, h, l, c, start, inc, mx):
    """pine_sar の1バー分。state=(result,maxmin,acc,below)。h,l,c は i 本目まで(i本目は部分足可)"""
    result, maxmin, acc, below = state
    first_trend = False
    if i == 1:
        if c[1] > c[0]:
            below, maxmin, result = True, h[1], l[0]
        else:
            below, maxmin, result = False, l[1], h[0]
        first_trend, acc = True, start
    result = result + acc * (maxmin - result)
    if below:
        if result > l[i]:
            first_trend, below = True, False
            result = max(h[i], maxmin); maxmin, acc = l[i], start
    else:
        if result < h[i]:
            first_trend, below = True, True
            result = min(l[i], maxmin); maxmin, acc = h[i], start
    if not first_trend:
        if below:
            if h[i] > maxmin:
                maxmin, acc = h[i], min(acc + inc, mx)
        else:
            if l[i] < maxmin:
                maxmin, acc = l[i], min(acc + inc, mx)
    if below:
        result = min(result, l[i - 1])
        if i > 1:
            result = min(result, l[i - 2])
    else:
        result = max(result, h[i - 1])
        if i > 1:
            result = max(result, h[i - 2])
    return result, (result, maxmin, acc, below)


def intrabar_exec(daily: pd.DataFrame, m: pd.DataFrame, fast=12, slow=26, sig=9, ps=(0.02, 0.02, 0.2)):
    """各営業日に『当月の部分足』で条件判定し、初めて成立した日の終値で約定。返り値 {Timestamp: ±1}"""
    full = signals(m, fast, slow, sig, ps)
    H, Lw, C = m.h.values, m.l.values, m.c.values
    e_f = pine_ema(C, fast); e_s = pine_ema(C, slow)
    macd_full = e_f - e_s; sig_full = pine_ema(macd_full, sig)
    a_f, a_s, a_g = 2 / (fast + 1), 2 / (slow + 1), 2 / (sig + 1)
    # 各バー終了時点の SAR 状態
    states = [None] * len(C)
    st = (np.nan, np.nan, np.nan, None)
    for i in range(1, len(C)):
        _, st = _sar_step(st, i, H, Lw, C, *ps)
        states[i] = st
    psar_full = full.psar.values
    regime = "out"; out = {}
    months = list(m.index)
    for i in range(2, len(C)):
        if np.isnan(sig_full[i - 1]):
            continue
        dd = daily.loc[str(months[i])]
        hh, ll = -np.inf, np.inf
        for day, row in dd.iterrows():
            hh, ll = max(hh, row.h), min(ll, row.l); cc = row.c
            ef = a_f * cc + (1 - a_f) * e_f[i - 1]; es = a_s * cc + (1 - a_s) * e_s[i - 1]
            mc = ef - es; sg = a_g * mc + (1 - a_g) * sig_full[i - 1]
            h2 = H.copy(); l2 = Lw.copy(); c2 = C.copy(); h2[i], l2[i], c2[i] = hh, ll, cc
            ps_i, _ = _sar_step(states[i - 1], i, h2, l2, c2, *ps)
            xo = mc > sg and macd_full[i - 1] <= sig_full[i - 1]
            xu = mc < sg and macd_full[i - 1] >= sig_full[i - 1]
            long_c = (ll > ps_i and xo) or (mc > sg and H[i - 1] < psar_full[i - 1] and hh > ps_i)
            prof_c = (hh < ps_i and xu) or (mc < sg and Lw[i - 1] > psar_full[i - 1] and ll < ps_i)
            if regime == "out" and long_c:
                out[day] = 1; regime = "long"; break
            if regime == "long" and prof_c:
                out[day] = -1; regime = "out"; break
    return out
