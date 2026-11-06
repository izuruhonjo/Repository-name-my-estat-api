"""改良検証の共通部品：データ読み込み、候補の実行、指標、世帯MC（B：目標ルール＋DC④、11/6実額起点）"""
import sys, math
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import s2engine as E, s2x as X, hh

TRAIN = ("2000-04-01", "2012-12-31")
TEST = ("2013-01-01", "2026-10-31")
D1 = "D1 DC④（○先進国株／×元本確保）"
# 11/6実額起点（mc_1106.py と同じ）
W0 = 19590431 + 19590432
_b = {"dc_f": 7803497.539782219, "dc_d": 890340.0}
D0 = _b["dc_f"] + _b["dc_d"]
N0 = 355464 * 2


class World:
    def __init__(self, data="data"):
        self.mkt = hh.load_all(data)
        self.A = hh.asset_returns(self.mkt)
        self.assets = E.build_assets(self.mkt)
        self.judg = {"base": E.judge_states(self.mkt), "buy6": E.judge_states(self.mkt, buy_lb=6)}
        self.ctx = {k: X.month_ctx_table(self.mkt, self.assets, j) for k, j in self.judg.items()}
        self.dc_nav = {}

    def dc(self, jkey):
        if jkey not in self.dc_nav:
            self.dc_nav[jkey] = hh.run_dc(self.mkt, self.A, self.judg[jkey], hh.DC_RULES[D1])[0]
        return self.dc_nav[jkey]

    def run(self, cfg_over=None, policy=None, jkey="base", **kw):
        cfg = X.XCfg(**{**(cfg_over or {}), **kw})
        if policy is not None:
            cfg.policy = policy
        return X.simulate_x(self.mkt, self.assets, self.judg[jkey], cfg, self.ctx[jkey])


def household(w: World, nav, states, jkey="base", goal=True, extra=None):
    T = hh.build_month_table(nav, states, {D1: w.dc(jkey)}, w.A, rate_daily=w.mkt["rate"])
    neg = E.negative_tilt_weights(T["S2"])
    kw = dict(dc_col=D1, cS2=0, cN=50_000, W0=W0, D0=D0, N0=N0, goal=goal)
    if extra:
        kw.update(extra)
    r = hh.hh_mc(T, **kw)
    rn = hh.hh_mc(T, weights=neg, **kw)
    rr = hh.hh_mc(T, start_idx=np.arange(0, len(T) - 60), **kw)
    r7 = hh.hh_mc(T, months=84, **kw)
    return dict(p5=r["p_hit"], p5_neg=rn["p_hit"], p5_hist=rr["p_hit"], p7=r7["p_hit"],
                med5=r["median"], p10_5=r["p10"], dd30=r["p_dd30"]), T


def evaluate(w: World, res, jkey="base", hh_goal=True):
    nav = res["nav"]
    m = X.indicators(nav)
    h1 = X.indicators(X.sub(nav, *TRAIN))
    h2 = X.indicators(X.sub(nav, *TEST))
    hhB, T = household(w, nav, res["states"], jkey, goal=hh_goal)
    out = dict(CAGR=m["CAGR"], Sortino=m["Sortino"], Sortino_std=m["Sortino_std"], MaxDD=m["MaxDD"],
               MaxDD_date=m["MaxDD_date"], Sharpe0=m["Sharpe0"], Calmar=m["Calmar"], WorstYear=m["WorstYear"],
               Min5y=m["Min5y"], CVaR95m=m["CVaR95m"],
               CAGR_h1=h1["CAGR"], CAGR_h2=h2["CAGR"], Sortino_h1=h1["Sortino"], Sortino_h2=h2["Sortino"],
               MaxDD_h1=h1["MaxDD"], MaxDD_h2=h2["MaxDD"],
               trades=res["n_trades"], trades_per_year=res["n_trades"] / m.get("Years", 26.58) if "Years" in m else res["n_trades"] / 26.58,
               tax_oku=res["tax_paid"] / 1e8, **hhB)
    return out, T
