"""
S2 改良検証用の拡張エンジン（s2engine.simulate の一般化）
=============================================================
・月末に「目標の持ち物（比率）」を policy(ctx) が決める。既定の policy は S2 そのもの。
・ボラ・ブレーキの売る割合・判定・戻し方、為替ブレーキ、TQQQ の混在、比率のずれのリバランスを追加。
・既定の設定では s2engine.simulate と日次NAVが完全一致する（imp_regress.py で確認）。
作成：2026-11-06
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Callable
import numpy as np
import pandas as pd
import s2engine as E

CORE = ("GP", "N1", "SV", "TQQQ", "QLD", "IEFJ")
RISKY = ("GP", "N1", "TQQQ", "QLD")
FUNDS = {"GP", "N1"}


@dataclass
class XCfg:
    start: str = "2000-04-01"
    end: str = "2026-10-31"
    init_jpy: float = 39_700_000
    exec_lag: int = 1
    slippage: float = 0.0
    # ボラ・ブレーキ
    vol_brake: bool = True
    brake_th: float = 0.30          # 20日ボラ（QQQ・ドル建て）の発動水準
    brake_frac: float = 0.5         # 発動時に投信（GP・N1）を売る割合
    brake_tqqq_all: bool = True     # TQQQ・QLD は発動時に全部売る
    restore: str = "month_end"      # "month_end"（現状）/ "daily"（ボラが restore_th 未満の翌営業日に戻す）
    restore_th: float = 0.25
    fx_brake: float | None = None   # USDJPY の20営業日変化がこれ以下（例 -0.05）でも発動
    geo_brake: tuple | None = None  # (金20日上昇率の下限, QQQ20日変化の上限) 例 (0.07, -0.05)
    # 月末の持ち物
    policy: Callable | None = None
    band: float = 0.05              # 目標比率とのずれがこれを超えたら月末にリバランス（混在時のみ）
    start_invested: bool = True     # 初日に目標の持ち物を買う（元エンジンは False：最初の持ち替えまで円現金）
    keep_brake_on_switch: bool = False  # ブレーキ中に持ち物が替わっても、ボラが高いままならブレーキを続ける


def default_policy(c: dict) -> dict:
    if c["state"] == "NORMAL":
        return {"GP": 1.0}
    if c["state"] == "DIP":
        return {"N1": 1.0}
    return {"SV": 1.0} if (c["sv_trend"] and c["sv_avail"]) else {"CASH": 1.0}


class Acct(E.Account):
    """E.Account に TaxBook・売買を流用。cfg は slippage を持つ XCfg を想定。"""
    pass


def _norm(w: dict) -> dict:
    w = {k: float(v) for k, v in w.items() if v > 1e-12}
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def month_ctx_table(mkt: pd.DataFrame, assets: pd.DataFrame, judg: pd.DataFrame, extra: dict | None = None) -> pd.DataFrame:
    """月末ごとの判断材料（policy に渡す）。すべて「その月末までに分かる値」。"""
    idx = judg.index
    rv = E.realized_vol(mkt["qqq"])
    fx = mkt["fx"]
    me = idx
    fxm = fx.loc[me]
    gold_jpy = (mkt["gold"] * mkt["fx"]).loc[me]
    ief_jpy = (1 + assets["SV"] * 0).cumprod()  # placeholder（下で上書き）
    ctx = pd.DataFrame(index=me)
    ctx["rv"] = rv.loc[me].values
    ctx["fx"] = fxm.values
    ctx["fx_sma12"] = fxm.shift(1).rolling(12).mean().values          # 当月を除く12ヶ月平均
    ctx["gold_jpy"] = gold_jpy.values
    ctx["gold_jpy_sma12"] = gold_jpy.shift(1).rolling(12).mean().values
    ctx["rate"] = mkt["rate"].loc[me].values
    q = mkt["qqq"].loc[me]
    ctx["qqq_sma10"] = q.rolling(10).mean().values                     # 当月を含む10ヶ月平均
    ctx["qqq_mom12"] = (q / q.shift(12) - 1).values
    if "smh" in mkt:
        s = mkt["smh"].loc[me]
        ctx["smh"] = s.values
        ctx["smh_sma10"] = s.rolling(10).mean().values
    # IEF 円建て（配当なし終値。トレンド判定だけに使う）
    iefj = (mkt["ief"] * mkt["fx"]).loc[me]
    ctx["ief_jpy"] = iefj.values
    ctx["ief_jpy_sma12"] = iefj.shift(1).rolling(12).mean().values
    if extra:
        for k, v in extra.items():
            ctx[k] = v.reindex(me).values
    return ctx


def simulate_x(mkt: pd.DataFrame, assets: pd.DataFrame, judg: pd.DataFrame, cfg: XCfg,
               ctx_table: pd.DataFrame | None = None, snapshots: bool = False) -> dict:
    idx = mkt.index
    i0 = idx.searchsorted(pd.Timestamp(cfg.start))
    i1 = idx.searchsorted(pd.Timestamp(cfg.end), side="right")
    cols = ["GP", "N1", "SV", "CASH", "TQQQ", "QLD", "QQQ1", "SOXL", "TMF", "SMH", "IEFJ"]
    a2 = assets.copy()
    if "IEFJ" not in a2:
        rfx = mkt["fx"].pct_change().fillna(0.0)
        ri = mkt["ief"].pct_change()
        a2["IEFJ"] = (((1 + ri) * (1 + rfx) - 1)).fillna(0.0)
    px_df = (1 + a2[cols]).cumprod()
    px_arr = {c: px_df[c].values for c in cols}
    sv_avail = assets["SV_avail"].values
    rv = E.realized_vol(mkt["qqq"]).values
    fx20 = (mkt["fx"] / mkt["fx"].shift(20) - 1).values
    g20 = (mkt["gold"] / mkt["gold"].shift(20) - 1).values
    q20 = (mkt["qqq"] / mkt["qqq"].shift(20) - 1).values
    me_set = {d: k for k, d in enumerate(judg.index)}
    policy = cfg.policy or default_policy
    if ctx_table is None:
        ctx_table = month_ctx_table(mkt, assets, judg)
    ctx_rows = ctx_table.to_dict("index")
    acct = E.Account(E.Cfg(init_jpy=cfg.init_jpy, slippage=cfg.slippage))

    def brake_cond(i):
        v = rv[i]
        c = (not np.isnan(v)) and v >= cfg.brake_th
        if cfg.fx_brake is not None and not np.isnan(fx20[i]) and fx20[i] <= cfg.fx_brake:
            c = True
        if cfg.geo_brake is not None and not np.isnan(g20[i]) and not np.isnan(q20[i]) \
                and g20[i] >= cfg.geo_brake[0] and q20[i] <= cfg.geo_brake[1]:
            c = True
        return c

    def mk_ctx(d, state, sv_trend, i):
        c = dict(ctx_rows.get(d, {}))
        c.update(state=state, sv_trend=sv_trend, sv_avail=bool(sv_avail[i]), date=d)
        return c

    # 初期状態
    j_prev = judg[judg.index < idx[i0]].dropna(subset=["state"])
    if len(j_prev):
        state = j_prev["state"].iloc[-1]
        sv_trend = bool(j_prev["sv_trend"].iloc[-1])
        d_prev = j_prev.index[-1]
    else:
        state, sv_trend, d_prev = "NORMAL", False, None
    target = _norm(policy(mk_ctx(d_prev, state, sv_trend, i0)))
    buy_flag = cfg.start_invested   # 目標に向けて買う（入金待ちの間も続ける）
    braked = False
    orders = []
    nav = np.zeros(i1 - i0)
    latent = np.zeros(i1 - i0)
    snaps = []
    state_arr = []
    n_rebal = 0
    n_brake = 0

    def total_value(px):
        return acct.value(px)

    def buy_to_target(px, d, i):
        """現金を目標比率の不足分に配る（入金待ちも含めた総額で目標額を計算）。"""
        if acct.cash <= 1:
            return
        V = total_value(px)
        defs = {}
        for k, w in target.items():
            if k == "CASH":
                continue
            if braked and k in RISKY:
                if not cfg.keep_brake_on_switch:
                    continue            # 元エンジンと同じ：ブレーキ中は危険資産を買わない
                keep = 0.0 if (k in ("TQQQ", "QLD") and cfg.brake_tqqq_all) else (1 - cfg.brake_frac)
                w = w * keep            # ブレーキ継続中の目標＝残す割合だけ
            held = acct.pos[k]["units"] * px[k] if k in acct.pos else 0.0
            defs[k] = max(w * V - held, 0.0)
        tot = sum(defs.values())
        if tot <= 1:
            return
        cash = acct.cash
        if len(defs) == 1:
            k = next(iter(defs))
            acct.buy(k, cash if defs[k] >= cash * (1 - 1e-9) else defs[k], px, d, i, log=False)  # 単一資産は元エンジンと同じく現金全額
            return
        for k, dv in defs.items():
            amt = cash * dv / tot if tot > cash else dv
            acct.buy(k, amt, px, d, i, log=False)

    for i in range(i0, i1):
        d = idx[i]
        px = {c: px_arr[c][i] for c in cols}
        acct.arrive(i)

        due = [o for o in orders if o[0] == i]
        orders = [o for o in orders if o[0] != i]
        for _, kind, payload in due:
            if kind == "REBAL":
                new_t = payload
                V = total_value(px)
                for a in [x for x in list(acct.pos) if x in CORE]:
                    w = new_t.get(a, 0.0)
                    val = acct.pos[a]["units"] * px[a]
                    if w <= 1e-12:
                        acct.sell(a, 1.0, px, d, i, is_fund=a in FUNDS)
                    elif val > w * V * (1 + 1e-9) and val > 0:
                        acct.sell(a, min(1.0, (val - w * V) / val), px, d, i, is_fund=a in FUNDS)
                target = new_t
                buy_flag = True
                # 元エンジン：持ち替えでブレーキ解除。keep_brake_on_switch なら、ボラが高いままの○では継続
                braked = bool(cfg.keep_brake_on_switch and braked and brake_cond(i - cfg.exec_lag)
                              and state in ("NORMAL", "DIP"))
                n_rebal += 1
            elif kind == "BRAKE_SELL":
                for a in [x for x in list(acct.pos) if x in RISKY]:
                    if a in FUNDS:
                        acct.sell(a, cfg.brake_frac, px, d, i, is_fund=True)
                    else:
                        acct.sell(a, 1.0 if cfg.brake_tqqq_all else cfg.brake_frac, px, d, i, is_fund=False)
                braked = True
                n_brake += 1
            elif kind == "BRAKE_RESTORE":
                buy_flag = True
                braked = False

        if buy_flag and acct.cash > 1:
            buy_to_target(px, d, i)
            if not acct.pending:
                buy_flag = False

        nav[i - i0] = total_value(px)
        g = sum(p_["units"] * px[k] - p_["cost"] for k, p_ in acct.pos.items())
        yr = d.year
        avail = sum(a for y, a in acct.tax.losses if yr - y <= 3)
        latent[i - i0] = max(g - avail, 0.0) * E.TAX
        if snapshots and d in me_set:
            snaps.append(dict(date=d, cash=acct.cash, pending=sum(a for _, a in acct.pending), losses=avail,
                              nav=nav[i - i0], latent=latent[i - i0],
                              **{f"{k}_units": acct.pos[k]["units"] if k in acct.pos else 0.0 for k in CORE},
                              **{f"{k}_cost": acct.pos[k]["cost"] if k in acct.pos else 0.0 for k in CORE},
                              **{f"{k}_px": px[k] for k in CORE}))
        state_arr.append((d, state, "+".join(f"{k}{v:.2f}" for k, v in target.items()), braked))

        # 日次：ブレーキ発動
        v = rv[i]
        if cfg.vol_brake and not braked and brake_cond(i):
            if state in ("NORMAL", "DIP") and any(a in acct.pos for a in RISKY):
                if not any(o[1] == "BRAKE_SELL" for o in orders):
                    orders.append((i + cfg.exec_lag, "BRAKE_SELL", None))
        # 日次：早い戻し
        if cfg.restore == "daily" and braked and d not in me_set and not np.isnan(v) and v < cfg.restore_th \
                and not brake_cond(i) and not any(o[1] in ("BRAKE_RESTORE", "REBAL") for o in orders):
            orders.append((i + cfg.exec_lag, "BRAKE_RESTORE", None))

        # 月末判定
        if d in me_set:
            row = judg.loc[d]
            if row["state"] is None or (isinstance(row["state"], float) and np.isnan(row["state"])):
                continue
            new_state = row["state"]
            new_trend = bool(row["sv_trend"])
            new_t = _norm(policy(mk_ctx(d, new_state, new_trend, i)))
            ex = i + cfg.exec_lag
            same_assets = set(new_t) == set(target)
            if not same_assets or max(abs(new_t.get(k, 0) - target.get(k, 0)) for k in set(new_t) | set(target)) > 1e-9:
                orders.append((ex, "REBAL", new_t))
            else:
                if braked and not brake_cond(i):
                    orders.append((ex, "BRAKE_RESTORE", None))
                elif (not braked) and len(target) > 1 and not acct.pending:
                    V = total_value(px)
                    dev = max(abs((acct.pos[k]["units"] * px[k] if k in acct.pos else 0.0) / V - w)
                              for k, w in target.items() if k != "CASH")
                    if dev > cfg.band:
                        orders.append((ex, "REBAL", dict(target)))
            if new_state == "RETREAT" and state == "RETREAT" and braked:
                braked = False
            state, sv_trend = new_state, new_trend

    nav_s = pd.Series(nav, index=idx[i0:i1])
    st = pd.DataFrame(state_arr, columns=["date", "state", "core", "braked"]).set_index("date")
    return {"nav": nav_s, "nav_liq": pd.Series(nav - latent, index=idx[i0:i1]), "states": st,
            "trades": acct.trades, "tax_paid": acct.tax.paid, "snaps": pd.DataFrame(snaps),
            "n_trades": acct.n_trades, "n_rebal": n_rebal, "n_brake": n_brake}


# ----------------------------------------------------------------------
# 指標
# ----------------------------------------------------------------------
def indicators(nav: pd.Series) -> dict:
    nav = nav.dropna()
    d = nav.pct_change().dropna()
    yrs = (nav.index[-1] - nav.index[0]).days / 365.25
    cagr = (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1
    # 引き継ぎメモと同じ定義（下落日の標準偏差）。浮動小数の丸めで出る −1e-16 の日は下落日に数えない（Excelと一致させるため）
    down = d[d < -1e-12].std() * math.sqrt(252)
    dd = nav / nav.cummax() - 1
    vol = d.std() * math.sqrt(252)
    m = nav.resample("ME").last()
    mr = m.pct_change().dropna()
    roll5 = (m / m.shift(60)) ** (1 / 5) - 1
    yr = nav.resample("YE").last()
    yr_ret = yr.pct_change()
    yr_ret.iloc[0] = yr.iloc[0] / nav.iloc[0] - 1
    # 標準的なソルティノ（目標0、全日数で割る下方偏差）も参考に
    dd_std = math.sqrt((np.minimum(d.values, 0) ** 2).mean()) * math.sqrt(252)
    return dict(CAGR=cagr, Sortino=cagr / down, Sortino_std=(d.mean() * 252) / dd_std, MaxDD=dd.min(),
                MaxDD_date=str(dd.idxmin().date()), Vol=vol, Sharpe0=cagr / vol, Calmar=cagr / abs(dd.min()),
                WorstYear=yr_ret.min(), Min5y=roll5.min(), Multiple=nav.iloc[-1] / nav.iloc[0],
                WorstMonth=mr.min(), CVaR95m=mr[mr <= mr.quantile(0.05)].mean())


def sub(nav, a, b):
    return nav[(nav.index >= a) & (nav.index <= b)]
