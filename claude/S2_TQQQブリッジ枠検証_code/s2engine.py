"""
S2 正典エンジン（再構築版） + TQQQブリッジ枠オーバーレイ
=============================================================
・日次シミュレーション、円建て、譲渡益税20.315%（損失3年繰越）、信託報酬、
  投信の入金待ち6営業日、判定翌営業日に執行。
・判定はQQQ（米ドル）の月末終値だけ。
・ブリッジ枠：S2が×のあいだ、待機資金の一部でレバETF（TQQQ等）を買い、
  ○に戻ったら売ってS2本体に合流。損切り・1回の×で最大2回まで。

作成：2026-11-05  本庄出（ZAD）戦略パートナー
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from dataclasses import dataclass, field

# ----------------------------------------------------------------------
# 1. データ
# ----------------------------------------------------------------------
# 米短期金利（年率%）の近似。FREDにアクセスできないため年次平均の近似値をハードコード
# （FF実効金利の年平均、2025-26は推定）。合成ゴールドプラス・合成TQQQの金利コストに使う。
SHORT_RATE_BY_YEAR = {
    1999: 4.97, 2000: 6.24, 2001: 3.88, 2002: 1.67, 2003: 1.13, 2004: 1.35,
    2005: 3.22, 2006: 4.97, 2007: 5.02, 2008: 1.92, 2009: 0.16, 2010: 0.18,
    2011: 0.10, 2012: 0.14, 2013: 0.11, 2014: 0.09, 2015: 0.13, 2016: 0.39,
    2017: 1.00, 2018: 1.83, 2019: 2.16, 2020: 0.37, 2021: 0.08, 2022: 1.68,
    2023: 5.02, 2024: 5.14, 2025: 4.30, 2026: 3.70,
}

FEES = {              # 年率
    "GP": 0.001991,   # Tracers NASDAQ100ゴールドプラス 信託報酬
    "N1": 0.002035,   # ニッセイNASDAQ100インデックス
    # 合成期間のコスト＝経費率＋実ETFとの乖離（2010〜2026の実データで較正：TQQQ −2.2pt/年、SOXL −9.3pt/年、TMF −4.9pt/年）
    "TQQQ": 0.0084 + 0.022,   # ProShares UltraPro QQQ（実データ期間は実価格を使用）
    "SOXL": 0.0075 + 0.093,
    "TMF": 0.0091 + 0.049,
    "QLD": 0.0095,
}
TAX = 0.20315
SETTLE_DAYS = 6       # 投信の売却代金が入るまでの営業日数


def _load_csv(path):
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date").set_index("date")
    return df["close"].astype(float)


def load_market(data_dir: str) -> pd.DataFrame:
    """QQQの取引日を基準に全系列を揃える。"""
    qqq = _load_csv(f"{data_dir}/QQQ.csv")
    idx = qqq.index
    out = pd.DataFrame({"qqq": qqq})
    for name, fn in [("fx", "USDJPY"), ("gold", "XAUUSD"), ("xlu", "XLU"), ("ief", "IEF"),
                     ("shy", "SHY"), ("tlt", "TLT"), ("tqqq", "TQQQ"), ("soxl", "SOXL"),
                     ("tmf", "TMF"), ("lqd", "LQD"), ("hyg", "HYG"), ("smh", "SMH")]:
        try:
            s = _load_csv(f"{data_dir}/{fn}.csv")
            out[name] = s.reindex(idx, method="ffill")  # 非営業日・欠損は前日値
        except FileNotFoundError:
            out[name] = np.nan
    out["rate"] = [SHORT_RATE_BY_YEAR.get(d.year, 3.0) / 100 for d in idx]
    return out


def build_assets(mkt: pd.DataFrame) -> pd.DataFrame:
    """各資産の日次リターン（円建て）。"""
    r = pd.DataFrame(index=mkt.index)
    rq = mkt["qqq"].pct_change().fillna(0.0)
    rfx = mkt["fx"].pct_change().fillna(0.0)
    rg = mkt["gold"].pct_change().fillna(0.0)
    rate_d = mkt["rate"] / 252.0
    jpy = lambda r_usd: (1 + r_usd) * (1 + rfx) - 1
    # 判定・シグナル用（ドル建て）
    r["qqq_usd"] = rq
    # ゴールドプラス：NASDAQ100 1倍＋金 1倍−短期金利−信託報酬（円建て）
    r["GP"] = jpy(rq) + jpy(rg) - rate_d - FEES["GP"] / 252
    r["N1"] = jpy(rq) - FEES["N1"] / 252
    # 守り待避 XLU50+IEF50（円建て、日次リバランス）。IEFが無い期間は現金扱い
    rx = mkt["xlu"].pct_change()
    ri = mkt["ief"].pct_change()
    sv = 0.5 * jpy(rx) + 0.5 * jpy(ri)
    r["SV"] = sv.fillna(0.0)
    r["SV_avail"] = mkt["ief"].notna() & mkt["xlu"].notna()
    r["CASH"] = 0.0
    # レバETF：実データがあれば実価格、無ければ合成（3×原資産−2×金利−経費）
    def lev(real_col, base_r_usd, fee, k=3):
        synth = k * base_r_usd - (k - 1) * rate_d - fee / 252
        real = mkt[real_col].pct_change() if real_col in mkt else pd.Series(np.nan, index=mkt.index)
        usd = real.where(real.notna() & mkt[real_col].shift(1).notna(), synth) if real_col in mkt else synth
        return jpy(usd), jpy(synth)
    r["TQQQ"], r["TQQQ_synth"] = lev("tqqq", rq, FEES["TQQQ"])
    r["QLD"] = jpy(2 * rq - rate_d - FEES["QLD"] / 252)
    r["QQQ1"] = jpy(rq)
    rs = mkt["smh"].pct_change().fillna(0.0)
    r["SOXL"], _ = lev("soxl", rs, FEES["SOXL"])
    rt = mkt["tlt"].pct_change().fillna(0.0)
    r["TMF"], _ = lev("tmf", rt, FEES["TMF"])
    r["SMH"] = jpy(rs)
    return r


# ----------------------------------------------------------------------
# 2. 月末判定（価格ブレーカー）
# ----------------------------------------------------------------------
def month_end_dates(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby([idx.year, idx.month]).last().values)


def judge_states(mkt: pd.DataFrame, sell_mult=0.85, buy_lb=9, high_lb=12, dip_th=-0.10,
                 sv_lb=12) -> pd.DataFrame:
    """各月末の判定表。state: NORMAL / DIP / RETREAT。"""
    me = month_end_dates(mkt.index)
    q = mkt.loc[me, "qqq"]
    # 守り待避の合成価格（円建て、XLU50+IEF50）→月末値の12ヶ月平均（当月除く）
    sv_px = (1 + build_assets(mkt)["SV"]).cumprod()
    svm = sv_px.loc[me]
    rows = []
    on = True
    for i, d in enumerate(me):
        if i < high_lb:
            rows.append((d, q.iloc[i], np.nan, np.nan, np.nan, None, np.nan))
            continue
        prev12 = q.iloc[i - high_lb:i]
        sell_line = prev12.max() * sell_mult
        buy_line = q.iloc[i - buy_lb:i].mean()
        high_incl = q.iloc[i - high_lb + 1:i + 1].max()
        dd = q.iloc[i] / high_incl - 1
        if on:
            if q.iloc[i] < sell_line:
                on = False
        else:
            if q.iloc[i] >= buy_line:
                on = True
        if on:
            state = "NORMAL" if dd >= dip_th else "DIP"
        else:
            state = "RETREAT"
        sv_trend = bool(svm.iloc[i] > svm.iloc[i - sv_lb:i].mean()) if i >= sv_lb else False
        rows.append((d, q.iloc[i], sell_line, buy_line, dd, state, sv_trend))
    df = pd.DataFrame(rows, columns=["date", "qqq", "sell_line", "buy_line", "dd12", "state", "sv_trend"]).set_index("date")
    return df


def realized_vol(close: pd.Series, n=20) -> pd.Series:
    return np.log(close).diff().rolling(n).std() * math.sqrt(252)


# ----------------------------------------------------------------------
# 3. 税金（損失繰越3年）
# ----------------------------------------------------------------------
class TaxBook:
    def __init__(self):
        self.losses = []   # (year, amount)
        self.paid = 0.0

    def settle(self, gain: float, year: int) -> float:
        """売却損益を申告。返り値は税額（>=0）。"""
        self.losses = [(y, a) for y, a in self.losses if year - y <= 3 and a > 1e-9]
        if gain <= 0:
            self.losses.append((year, -gain))
            return 0.0
        taxable = gain
        new = []
        for y, a in self.losses:
            use = min(a, taxable)
            taxable -= use
            if a - use > 1e-9:
                new.append((y, a - use))
        self.losses = new
        tax = taxable * TAX
        self.paid += tax
        return tax


# ----------------------------------------------------------------------
# 4. 口座シミュレーション
# ----------------------------------------------------------------------
@dataclass
class BridgeCfg:
    enabled: bool = False
    asset: str = "TQQQ"
    budget_pct: float = 0.20       # ×中の待機資金に対する割合
    stop_loss: float = 0.25        # 取得値からの下落率で損切り
    max_entries: int = 2           # 1回の×で最大回数
    signal: pd.Series | None = None  # True の日に（翌営業日執行で）買う
    also_volbrake: bool = False    # ボラ・ブレーキ中の待機現金にも使う
    take_profit: float | None = None  # 取得値からの上昇率で利確（Noneなら○復帰まで）
    recovery_months: int = 0       # >0 なら「×→○の切替時」にレバETFを budget_pct だけ買い、Nヶ月後に本体へ合流（ブリッジの代替案）


@dataclass
class Cfg:
    start: str = "2000-04-01"
    end: str = "2026-10-31"
    init_jpy: float = 39_700_000
    exec_lag: int = 1              # 判定からの執行営業日数
    slippage: float = 0.0          # 片道コスト（割合）
    vol_th: float = 0.30
    vol_brake: bool = True
    vol_brake_in_retreat: bool = False
    bridge: BridgeCfg = field(default_factory=BridgeCfg)


class Account:
    """1口座（夫婦で同じ判定なので1口座で代表）。"""

    def __init__(self, cfg: Cfg):
        self.cfg = cfg
        self.cash = cfg.init_jpy
        self.pending = []       # (arrive_idx, amount)
        self.pos = {}           # asset -> dict(units, cost)  units=円建てNAV1.0換算の口数
        self.tax = TaxBook()
        self.trades = []        # (date, asset, side, amount, pnl_after_tax)
        self.n_trades = 0

    # NAV は資産ごとの累積指数（price）で管理
    def value(self, px: dict) -> float:
        v = self.cash + sum(a for _, a in self.pending)
        for k, p in self.pos.items():
            v += p["units"] * px[k]
        return v

    def buy(self, asset, amount, px, date, i, log=True):
        amount = min(amount, self.cash)
        if amount <= 1.0:
            return 0.0
        cost = amount * (1 - self.cfg.slippage)
        units = cost / px[asset]
        p = self.pos.setdefault(asset, {"units": 0.0, "cost": 0.0})
        p["units"] += units
        p["cost"] += amount
        self.cash -= amount
        self.n_trades += 1
        if log:
            self.trades.append((date, asset, "BUY", amount, 0.0))
        return amount

    def sell(self, asset, frac, px, date, i, is_fund: bool):
        p = self.pos.get(asset)
        if not p or p["units"] <= 0:
            return 0.0
        units = p["units"] * frac
        gross = units * px[asset] * (1 - self.cfg.slippage)
        cost = p["cost"] * frac
        gain = gross - cost
        tax = self.tax.settle(gain, date.year)
        net = gross - tax
        p["units"] -= units
        p["cost"] -= cost
        if p["units"] <= 1e-12:
            del self.pos[asset]
        if is_fund:
            self.pending.append((i + SETTLE_DAYS, net))
        else:
            self.cash += net
        self.n_trades += 1
        self.trades.append((date, asset, "SELL", gross, gain - tax))
        return net

    def arrive(self, i):
        keep = []
        for a_i, amt in self.pending:
            if a_i <= i:
                self.cash += amt
            else:
                keep.append((a_i, amt))
        self.pending = keep


FUNDS = {"GP", "N1"}


def simulate(mkt: pd.DataFrame, assets: pd.DataFrame, judg: pd.DataFrame, cfg: Cfg) -> dict:
    """S2（＋ブリッジ枠）を日次で回す。返り値：日次評価額、トレード、状態列。"""
    idx = mkt.index
    i0 = idx.searchsorted(pd.Timestamp(cfg.start))
    i1 = idx.searchsorted(pd.Timestamp(cfg.end), side="right")
    cols = ["GP", "N1", "SV", "CASH", "TQQQ", "QLD", "QQQ1", "SOXL", "TMF", "SMH"]
    px_df = (1 + assets[cols]).cumprod()
    px_arr = {c: px_df[c].values for c in cols}
    sv_avail = assets["SV_avail"].values
    rv = realized_vol(mkt["qqq"]).values
    qqq = mkt["qqq"].values
    me_set = {d: k for k, d in enumerate(judg.index)}
    acct = Account(cfg)
    b = cfg.bridge
    sig = b.signal.reindex(idx).fillna(False).values if (b.enabled and b.signal is not None) else None

    # 状態
    state = None          # NORMAL/DIP/RETREAT
    sv_trend = False
    target_core = None    # 本体で持つべき資産
    braked = False        # ボラ・ブレーキ中
    orders = []           # (exec_idx, kind, payload)
    bridge_entries = 0    # 今回の×での発動回数
    bridge_entry_px = None
    bridge_on = False
    in_episode = False    # ×（またはブレーキ）中か
    nav = np.zeros(i1 - i0)
    state_arr = []
    bridge_log = []

    # 初期状態：開始日直前の月末判定
    j_prev = judg[judg.index < idx[i0]].dropna(subset=["state"])
    if len(j_prev):
        state = j_prev["state"].iloc[-1]
        sv_trend = bool(j_prev["sv_trend"].iloc[-1])
    else:
        state = "NORMAL"
    def core_for(state, sv_trend, i):
        if state == "NORMAL":
            return "GP"
        if state == "DIP":
            return "N1"
        return "SV" if (sv_trend and sv_avail[i]) else "CASH"
    target_core = core_for(state, sv_trend, i0)
    pending_core_buy = None     # 入金待ちのあと買う資産
    bridge_wait = None          # 入金待ちのあと買うブリッジ金額（割合）
    recovery_pending = False    # 回復レバの買い待ち

    for i in range(i0, i1):
        d = idx[i]
        px = {c: px_arr[c][i] for c in cols}
        acct.arrive(i)

        # --- 当日執行の注文 ---
        due = [o for o in orders if o[0] == i]
        orders = [o for o in orders if o[0] != i]
        for _, kind, payload in due:
            if kind == "SWITCH":          # 本体の持ち替え
                new_core = payload
                old = [a for a in acct.pos if a in ("GP", "N1", "SV")]
                for a in old:
                    acct.sell(a, 1.0, px, d, i, is_fund=a in FUNDS)
                target_core = new_core
                pending_core_buy = new_core
                braked = False
            elif kind == "BRAKE_SELL":
                for a in [x for x in acct.pos if x in ("GP", "N1")]:
                    acct.sell(a, 0.5, px, d, i, is_fund=True)
                braked = True
            elif kind == "BRAKE_RESTORE":
                pending_core_buy = target_core
                braked = False
            elif kind == "BRIDGE_BUY":
                frac = payload
                if not in_episode:
                    continue
                total_wait = acct.cash + sum(a for _, a in acct.pending) + \
                    sum(acct.pos[a]["units"] * px[a] for a in acct.pos if a == "SV")
                amt = frac * total_wait
                if acct.cash < amt and "SV" in acct.pos:
                    need = amt - acct.cash
                    svv = acct.pos["SV"]["units"] * px["SV"]
                    acct.sell("SV", min(1.0, need / svv), px, d, i, is_fund=False)
                if acct.cash + 1 < amt and acct.pending:
                    bridge_wait = frac       # 入金待ち後に買う
                    continue
                got = acct.buy(b.asset, amt, px, d, i)
                if got > 0:
                    bridge_on = True
                    bridge_entry_px = px[b.asset]
                    bridge_entries += 1
                    bridge_log.append((d, "BUY", got, px[b.asset], None))
            elif kind == "RECOVERY_FLAG":
                recovery_pending = True
            elif kind == "BRIDGE_SELL":
                if b.asset in acct.pos:
                    before = acct.pos[b.asset]["cost"]
                    net = acct.sell(b.asset, 1.0, px, d, i, is_fund=False)
                    bridge_log.append((d, payload, net, px[b.asset], net - before))
                bridge_on = False
                if payload == "EXIT_TO_CORE":
                    pending_core_buy = target_core

        # 入金待ち後のブリッジ買い
        if bridge_wait is not None and in_episode and not bridge_on and not acct.pending and acct.cash > 1:
            frac = bridge_wait
            bridge_wait = None
            amt = frac * acct.cash
            got = acct.buy(b.asset, amt, px, d, i)
            if got > 0:
                bridge_on = True
                bridge_entry_px = px[b.asset]
                bridge_entries += 1
                bridge_log.append((d, "BUY", got, px[b.asset], None))
        elif bridge_wait is not None and not in_episode:
            bridge_wait = None

        # 回復レバ：現金が入った時点で先にレバETFを買う
        if recovery_pending and acct.cash > 1 and not acct.pending:
            recovery_pending = False
            got = acct.buy(b.asset, b.budget_pct * acct.value(px), px, d, i)
            if got > 0:
                bridge_on = True; bridge_entry_px = px[b.asset]
                bridge_log.append((d, "BUY", got, px[b.asset], None))
                orders.append((i + 21 * b.recovery_months, "BRIDGE_SELL", "EXIT_TO_CORE"))
        # 本体の買い（現金があるとき。入金待ち分は到着後に順次）
        if pending_core_buy is not None and acct.cash > 1:
            if not (braked and pending_core_buy in ("GP", "N1")):
                if pending_core_buy == "CASH":
                    pass
                else:
                    # ブリッジ中の×では、ブリッジに回していない分だけ本体へ
                    acct.buy(pending_core_buy, acct.cash, px, d, i, log=False)
            if not acct.pending:
                pending_core_buy = None

        # --- 評価 ---
        nav[i - i0] = acct.value(px)
        state_arr.append((d, state, target_core, braked, bridge_on))

        # --- 日次：ボラ・ブレーキ発動 ---
        v = rv[i]
        if cfg.vol_brake and not braked and not np.isnan(v) and v >= cfg.vol_th:
            if state in ("NORMAL", "DIP") and any(a in acct.pos for a in ("GP", "N1")):
                if not any(o[1] == "BRAKE_SELL" for o in orders):
                    orders.append((i + cfg.exec_lag, "BRAKE_SELL", None))
                    if b.enabled and b.also_volbrake:
                        in_episode = True
                        bridge_entries = 0

        # --- 日次：ブリッジ損切り／利確 ---
        if b.enabled and bridge_on and bridge_entry_px is not None:
            cur = px[b.asset] / bridge_entry_px - 1
            if cur <= -b.stop_loss and not any(o[1] == "BRIDGE_SELL" for o in orders):
                orders.append((i + cfg.exec_lag, "BRIDGE_SELL", "STOP"))
            elif b.take_profit is not None and cur >= b.take_profit and not any(o[1] == "BRIDGE_SELL" for o in orders):
                orders.append((i + cfg.exec_lag, "BRIDGE_SELL", "TP"))

        # --- 日次：ブリッジ買いシグナル ---
        if b.enabled and in_episode and not bridge_on and bridge_wait is None and bridge_entries < b.max_entries \
                and sig is not None and sig[i] and not any(o[1] in ("BRIDGE_BUY", "BRIDGE_SELL") for o in orders):
            orders.append((i + cfg.exec_lag, "BRIDGE_BUY", b.budget_pct))

        # --- 月末判定 ---
        if d in me_set:
            row = judg.loc[d]
            if row["state"] is None or (isinstance(row["state"], float) and np.isnan(row["state"])):
                continue
            new_state = row["state"]
            new_trend = bool(row["sv_trend"])
            new_core = core_for(new_state, new_trend, i)
            ex = i + cfg.exec_lag
            if new_core != target_core:
                # ブリッジ中なら先に売って本体へ合流
                if b.enabled and (bridge_on or bridge_wait is not None) and new_state != "RETREAT":
                    orders.append((ex, "BRIDGE_SELL", "EXIT_TO_CORE"))
                    bridge_wait = None
                orders.append((ex, "SWITCH", new_core))
                if b.enabled and b.recovery_months > 0 and state == "RETREAT" and new_state != "RETREAT":
                    orders.append((ex, "RECOVERY_FLAG", None))
                if new_state == "RETREAT" and state != "RETREAT":
                    in_episode = True
                    bridge_entries = 0
                if new_state != "RETREAT":
                    in_episode = False if not (b.also_volbrake and braked) else in_episode
            else:
                # 同じ持ち物。ブレーキ中で月末ボラ<30%なら全額へ戻す
                if braked and not np.isnan(v) and v < cfg.vol_th:
                    orders.append((ex, "BRAKE_RESTORE", None))
                    if b.enabled and b.also_volbrake and bridge_on:
                        orders.append((ex, "BRIDGE_SELL", "EXIT_TO_CORE"))
                    if b.also_volbrake and state != "RETREAT":
                        in_episode = False
            if new_state == "RETREAT" and state == "RETREAT" and braked:
                braked = False
            state, sv_trend = new_state, new_trend

    nav_s = pd.Series(nav, index=idx[i0:i1])
    st = pd.DataFrame(state_arr, columns=["date", "state", "core", "braked", "bridge"]).set_index("date")
    return {"nav": nav_s, "states": st, "trades": acct.trades, "bridge_log": bridge_log,
            "tax_paid": acct.tax.paid, "n_trades": acct.n_trades}


# ----------------------------------------------------------------------
# 5. 指標
# ----------------------------------------------------------------------
def metrics(nav: pd.Series) -> dict:
    nav = nav.dropna()
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1
    dd = nav / nav.cummax() - 1
    m = nav.resample("ME").last()
    mr = m.pct_change().dropna()
    yr = m.groupby(m.index.year).last()
    yr_ret = yr.pct_change().dropna()
    first_year = nav.index[0].year
    if first_year not in yr_ret.index and first_year in yr.index:
        yr_ret.loc[first_year] = yr.loc[first_year] / nav.iloc[0] - 1
    yr_ret = yr_ret.sort_index()
    roll5 = (m / m.shift(60)) ** (1 / 5) - 1
    sharpe = mr.mean() / mr.std() * math.sqrt(12) if mr.std() > 0 else np.nan
    return {"CAGR": cagr, "MaxDD": dd.min(), "WorstYear": yr_ret.min(), "WorstYearY": int(yr_ret.idxmin()),
            "Min5yCAGR": roll5.min(), "Multiple": nav.iloc[-1] / nav.iloc[0], "Sharpe": sharpe,
            "Vol": mr.std() * math.sqrt(12), "Years": yrs}


def monthly_returns(nav: pd.Series) -> pd.Series:
    return nav.resample("ME").last().pct_change().dropna()


# ----------------------------------------------------------------------
# 6. モンテカルロ（12ヶ月ブロック・ブートストラップ）
# ----------------------------------------------------------------------
def monte_carlo(mr: pd.Series, years: int, n_paths=20000, seed=42, start=39_700_000,
                target=100_000_000, weights=None, dd_th=-0.30):
    """mr: 月次リターン。12ヶ月ブロックを復元抽出。weights: ブロック開始月の重み（ネガ寄せ用）。"""
    rng = np.random.default_rng(seed)
    r = mr.values
    n = len(r)
    block = 12
    starts = np.arange(0, n - block + 1)
    if weights is None:
        w = np.ones(len(starts))
    else:
        w = np.asarray(weights)[: len(starts)]
    w = w / w.sum()
    nb = years
    pick = rng.choice(starts, size=(n_paths, nb), p=w)
    paths = np.empty((n_paths, nb * block))
    for k in range(nb):
        for j in range(block):
            paths[:, k * block + j] = r[pick[:, k] + j]
    cum = start * np.cumprod(1 + paths, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.full((n_paths, 1), start), cum], axis=1), axis=1)[:, 1:]
    dd = cum / peak - 1
    return {
        "median": float(np.median(cum[:, -1])),
        "p10": float(np.percentile(cum[:, -1], 10)),
        "p_hit_target": float((cum.max(axis=1) >= target).mean()),
        "p_dd_over": float((dd.min(axis=1) <= dd_th).mean()),
        "cagr_median": float(np.median((cum[:, -1] / start) ** (1 / years) - 1)),
    }


def negative_tilt_weights(mr: pd.Series, mult=2.5):
    """ITバブル崩壊（2000-04〜2002-09）とリーマン（2007-11〜2009-03）を含む開始月を重く。"""
    idx = mr.index
    w = np.ones(len(idx))
    for a, b_ in [("2000-04-01", "2002-09-30"), ("2007-11-01", "2009-03-31")]:
        m = (idx >= a) & (idx <= b_)
        w[m] = mult
    return w


# ----------------------------------------------------------------------
# 7. 過学習の確率（PBO, CSCV）と Deflated Sharpe Ratio
# ----------------------------------------------------------------------
def pbo_cscv(M: np.ndarray, S=16) -> float:
    """M: (T, N) 候補戦略の月次リターン行列。Bailey et al. (2017)。"""
    from itertools import combinations
    T, N = M.shape
    T = T - T % S
    M = M[:T]
    blocks = np.array_split(np.arange(T), S)
    logits = []
    for comb in combinations(range(S), S // 2):
        tr = np.concatenate([blocks[c] for c in comb])
        te = np.concatenate([blocks[c] for c in range(S) if c not in comb])
        def sr(x):
            s = x.std(axis=0)
            return np.where(s > 0, x.mean(axis=0) / np.where(s > 0, s, 1), -np.inf)
        best = np.argmax(sr(M[tr]))
        rank = (sr(M[te]) < sr(M[te])[best]).sum() + 1
        w = rank / (N + 1)
        w = min(max(w, 1e-6), 1 - 1e-6)
        logits.append(math.log(w / (1 - w)))
    logits = np.array(logits)
    return float((logits <= 0).mean())


def deflated_sharpe(sr_obs_monthly: float, n_trials: int, sr_var_trials: float, T: int,
                    skew: float, kurt: float) -> float:
    """Bailey & López de Prado (2014)。返り値は確率（>0.95なら有意）。SRは月次（年率化前）。"""
    from scipy.stats import norm
    em = 0.5772156649
    sr0 = math.sqrt(sr_var_trials) * ((1 - em) * norm.ppf(1 - 1 / n_trials) + em * norm.ppf(1 - 1 / (n_trials * math.e)))
    denom = math.sqrt(1 - skew * sr_obs_monthly + (kurt - 1) / 4 * sr_obs_monthly ** 2)
    if denom <= 0:
        return float("nan")
    z = (sr_obs_monthly - sr0) * math.sqrt(T - 1) / denom
    return float(norm.cdf(z))
