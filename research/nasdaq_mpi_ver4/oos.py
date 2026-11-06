"""アウトオブサンプル(OOS)検証: 改良案①「高金利期はレバ2倍」②「月末引けで約定」

設計（事前に固定し、OOSを見てから変えない）
  IS(作成に使った期間)   : NDX 1985/10〜2026/10  … 記事のルールも改良案も、この期間を見て作られた
  OOS-時間(使っていない期間): S&P500 1950/1〜1985/9, NASDAQ総合 1974/1〜1985/9（NDX誕生前・高金利期を含む）
  OOS-事後(記事公開後)   : NDX 2022/9〜2026/10（記事ルールにとってのみOOS。改良案はこの期間も見ている）
  OOS-資産(同時期の別指数): S&P500 1985/10〜, ダウ 1995/1〜, ラッセル2000 1991/1〜（〜2026/10）
  ① 閾値はISだけで選ぶ（グリッド: 2〜6%, entry/monthly）→ そのままOOSに適用
  ② 3方式: 翌営業日引け(C, 基準) / 月末引け(C-MOC, 当日終値で判定) / 現実的MOC(前日終値までで判定→月末引け)
  評価: 全期間 + 10年ローリング窓（毎年1月開始）の勝率・中央値。窓は重複するので独立ではない（記述統計）
"""
import sys
sys.path.insert(0, ".")
from mpi import *
from mpi import _sar_step

SHILLER = DATA / "shiller_sp500.csv"


# ------------------------------------------------------------------ data
def rf_series(idx):
    d = load_fred("DTB3")
    m = load_fred("TB3MS")                    # 1934〜 月次（DTB3は1954〜）
    comb = pd.concat([m[m.index < d.index[0]], d]).sort_index()
    comb = comb[~comb.index.duplicated(keep="last")]
    return comb.reindex(comb.index.union(idx)).ffill().reindex(idx).values / 100.0


def fx_series(idx):
    f = load_fred("DEXJPUS")
    v = f.reindex(f.index.union(idx)).ffill().reindex(idx)
    return v.fillna(360.0).values               # 1971/1以前は固定相場360円


def shiller_yield(idx):
    s = pd.read_csv(SHILLER, parse_dates=["Date"]).set_index("Date")
    y = (s.Dividend / s.SP500).replace(0, np.nan).dropna()     # 年率配当利回り（月次）
    return y.reindex(y.index.union(idx)).ffill().reindex(idx).values


def build_daily_idx(sym, div_etf=None, shiller_mult=None):
    """sym の日次 + rf + fx + 1倍の日次配当利回り dy。
    dy: div_etf の adj/close 比（ETF上場後）→ それ以前は Shiller S&P500利回り × shiller_mult"""
    ix = load_yahoo(sym)
    idx = ix.index
    df = pd.DataFrame(index=idx)
    df["c"] = ix.c
    for k in "ohl":                               # 古い期間は O/H/L 欠損 or 0 → 終値で代用
        v = ix[k].where(ix[k] > 0)
        df[k] = v.fillna(ix.c)
    df["h"] = df[["h", "c"]].max(axis=1); df["l"] = df[["l", "c"]].min(axis=1)
    df = df[["o", "h", "l", "c"]]
    df["r"] = df.c.pct_change().fillna(0.0)
    df["dt"] = df.index.to_series().diff().dt.days.fillna(1).astype(float)
    df["rf"] = rf_series(idx)
    df["fx"] = fx_series(idx)
    dy = np.zeros(len(idx))
    if shiller_mult is not None:
        dy = shiller_yield(idx) * shiller_mult * df.dt.values / 365.0
    if div_etf is not None:
        e = load_yahoo(div_etf).reindex(idx)
        ratio = e.adj / e.c
        de = (ratio / ratio.shift(1) - 1).clip(lower=0)
        ok = (idx > load_yahoo(div_etf).index[0])
        dy = np.where(ok, de.fillna(0.0).values, dy)
    df["dy"] = np.nan_to_num(dy)
    return df


# ------------------------------------------------------------------ 現実的MOC: 前日終値までの部分足で判定 → 月末最終日の引けで約定
def tm1_exec(daily, m, fast=12, slow=26, sig=9, ps=(0.02, 0.02, 0.2)):
    full = signals(m, fast, slow, sig, ps)
    H, Lw, C = m.h.values, m.l.values, m.c.values
    e_f = pine_ema(C, fast); e_s = pine_ema(C, slow)
    macd_full = e_f - e_s; sig_full = pine_ema(macd_full, sig)
    a_f, a_s, a_g = 2 / (fast + 1), 2 / (slow + 1), 2 / (sig + 1)
    states = [None] * len(C); st = (np.nan, np.nan, np.nan, None)
    for i in range(1, len(C)):
        _, st = _sar_step(st, i, H, Lw, C, *ps); states[i] = st
    psar_full = full.psar.values
    regime, out = "out", {}
    months = list(m.index)
    for i in range(2, len(C)):
        if np.isnan(sig_full[i - 1]) or np.isnan(psar_full[i - 1]):
            continue
        dd = daily.loc[str(months[i])]
        if len(dd) < 2:
            continue
        part = dd.iloc[:-1]                       # 最終営業日を除く（＝前日終値まで）
        hh, ll, cc = part.h.max(), part.l.min(), part.c.iloc[-1]
        ef = a_f * cc + (1 - a_f) * e_f[i - 1]; es = a_s * cc + (1 - a_s) * e_s[i - 1]
        mc = ef - es; sg = a_g * mc + (1 - a_g) * sig_full[i - 1]
        h2, l2, c2 = H.copy(), Lw.copy(), C.copy(); h2[i], l2[i], c2[i] = hh, ll, cc
        ps_i, _ = _sar_step(states[i - 1], i, h2, l2, c2, *ps)
        xo = mc > sg and macd_full[i - 1] <= sig_full[i - 1]
        xu = mc < sg and macd_full[i - 1] >= sig_full[i - 1]
        long_c = (ll > ps_i and xo) or (mc > sg and H[i - 1] < psar_full[i - 1] and hh > ps_i)
        prof_c = (hh < ps_i and xu) or (mc < sg and Lw[i - 1] > psar_full[i - 1] and ll < ps_i)
        if regime == "out" and long_c:
            out[dd.index[-1]] = 1; regime = "long"
        elif regime == "long" and prof_c:
            out[dd.index[-1]] = -1; regime = "out"
    return out


# ------------------------------------------------------------------ datasets
def datasets():
    ndx = build_daily()                          # 既存検証と同一（QQQ配当、1999/3以前0.4%）
    gspc = build_daily_idx("GSPC", div_etf="SPY", shiller_mult=1.0)
    ixic = build_daily_idx("IXIC", shiller_mult=0.5)       # 仮定: NASDAQ総合の利回り = S&P500 の半分
    dji = build_daily_idx("DJI", div_etf="DIA", shiller_mult=1.0)
    rut = build_daily_idx("RUT", div_etf="IWM", shiller_mult=0.6)  # 仮定: 2000/5以前は S&P500 の0.6倍
    return dict(NDX=ndx, GSPC=gspc, IXIC=ixic, DJI=dji, RUT=rut)


# 較正: 各指数の実在3倍/2倍ETF（IXICはNDX連動ETFで較正した値を流用）
CAL = dict(NDX=("TQQQ", "QLD"), GSPC=("UPRO", "SSO"), DJI=("UDOW", "DDM"), RUT=("TNA", "UWM"))

SETS = [  # (ラベル, 区分, 指数, 開始, 終了)
    ("NDX 1985-2026", "IS", "NDX", "1985-10", "2026-10"),
    ("S&P500 1950-1985", "OOS-時間", "GSPC", "1950-01", "1985-09"),
    ("NASDAQ総合 1974-1985", "OOS-時間", "IXIC", "1974-01", "1985-09"),
    ("NDX 2022/9-2026", "OOS-事後", "NDX", "2022-09", "2026-10"),
    ("S&P500 1985-2026", "OOS-資産", "GSPC", "1985-10", "2026-10"),
    ("ダウ 1995-2026", "OOS-資産", "DJI", "1995-01", "2026-10"),
    ("ラッセル2000 1991-2026", "OOS-資産", "RUT", "1991-01", "2026-10"),
]
THR = [0.02, 0.03, 0.04, 0.05, 0.06]


def base_cfg(c3, c2):
    C = Cfg(name="C", lev_cost=c3, lev_cost_lo=c2, financing=True, one_er=0.0015, dividends=True, exec_lag=1,
            contrib_at_month_end=False, commission=0.00495, comm_cap_usd=22, slippage=0.0002, fx=True,
            jp_tax=True, div_tax=True, infl_adj=False)
    return C


def variants_rate(C):
    v = {"3倍固定": C, "2倍固定": replace(C, rate_thr=-1.0)}
    for t in THR:
        for mode in ["entry", "monthly"]:
            v[f"{t:.0%}超→2倍({mode})"] = replace(C, rate_thr=t, rate_mode=mode)
    return v


def variants_exec(C):
    return {"翌営業日引け(C)": (C, None),
            "月末引け(C-MOC)": (replace(C, exec_lag=0, contrib_at_month_end=True), None),
            "現実的MOC(前日判定)": (replace(C, exec_lag=0, contrib_at_month_end=True), "tm1"),
            "分解:約定だけ月末": (replace(C, exec_lag=0), None),
            "分解:積立だけ月末": (replace(C, contrib_at_month_end=True), None)}


def windows(start, end, years=10):
    s0, e0 = pd.Period(start, "M"), pd.Period(end, "M")
    out = []
    y = s0.year if s0.month == 1 else s0.year + 1
    while pd.Period(f"{y + years - 1}-12", "M") <= e0:
        out.append((f"{y}-01", f"{y + years - 1}-12")); y += 1
    return out


def one(daily, sig, cfg, ex):
    r, h, t = run(daily, sig, cfg, exec_dates=ex)
    return dict(final=r["final_after_liq"], contrib=r["contrib"], irr=r["irr"], mdd=r["mdd_twr"],
                trades=r["n_trades"], switches=r["n_switch"], share2=r["share_2x"])


def main():
    D = datasets()
    cost = {}
    for k, (e3, e2) in CAL.items():
        cost[k] = (calibrate_cost(D[k], e3, 3)[0], calibrate_cost(D[k], e2, 2)[0])
    cost["IXIC"] = cost["NDX"]
    SIG, TM1 = {}, {}
    for k, d in D.items():
        m = monthly_bars(d).loc[:"2026-10"]
        SIG[k] = signals(m); TM1[k] = tm1_exec(d, m)
    rows = []
    for lab, kind, k, st, en in SETS:
        C = replace(base_cfg(*cost[k]), start=st, end=en)
        wins = [("全期間", st, en)] + [("10年窓", a, b) for a, b in windows(st, en)]
        for wl, a, b in wins:
            for vn, cfg in variants_rate(C).items():
                rows.append(dict(set=lab, kind=kind, idx=k, test="①金利ルール", win=wl, start=a, end=b, var=vn,
                                 **one(D[k], SIG[k], replace(cfg, start=a, end=b), None)))
            for vn, (cfg, ex) in variants_exec(C).items():
                if vn == "翌営業日引け(C)":
                    continue  # = 3倍固定 と同一
                rows.append(dict(set=lab, kind=kind, idx=k, test="②約定", win=wl, start=a, end=b, var=vn,
                                 **one(D[k], SIG[k], replace(cfg, start=a, end=b), TM1[k] if ex else None)))
            for dv in ["dca1", "dca3"]:
                rows.append(dict(set=lab, kind=kind, idx=k, test="参考", win=wl, start=a, end=b,
                                 var={"dca1": "1倍単純積立", "dca3": "3倍単純積立"}[dv],
                                 **one(D[k], SIG[k], replace(C, start=a, end=b, strategy=dv), None)))
        print(lab, "done", flush=True)
    res = pd.DataFrame(rows)
    # シグナル比較（当日判定 vs 前日判定）
    agree = []
    for k in D:
        s = SIG[k]; full = {r.last_day: int(r.sig) for _, r in s[s.sig != 0].iterrows()}
        t1 = TM1[k]
        agree.append(dict(idx=k, n_full=len(full), n_tm1=len(t1), same=len(set(full.items()) & set(t1.items()))))
    pd.to_pickle(dict(res=res, cost=cost, agree=pd.DataFrame(agree), sig={k: SIG[k] for k in D}, tm1=TM1),
                 "data/oos.pkl")
    for k in D:
        D[k].to_pickle(f"data/daily_{k}.pkl")
    return res


if __name__ == "__main__":
    main()
