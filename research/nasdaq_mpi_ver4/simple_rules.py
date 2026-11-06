"""次の候補5: MACD＋パラボリック(ver4.0)の複雑さに意味はあるか — 単純な暴落回避ルールとの比較（100万円一括スタート）

設計（結果を見る前に固定）
  資金: 主ケース = 100万円を初日に一括投資・積立なし。感応度 = 100万円 + 月3万円（月初）。
  コスト: 現実コストC（SBI手数料・為替・日本税制・較正コスト）。シグナルは月足の締め日の翌営業日の引けで約定。
  運用の仕組みは全ルール共通（ver4.0と同じ）: 買い = 全額を3倍へ / 売り = 3倍を全売却し現金、毎月その1%を1倍へ。
    シグナルの作り方だけを入れ替える。
  開始時の状態: 開始前のシグナル履歴で決める（最後のシグナルが買いなら3倍で開始）。一括投資では開始時の状態が効くため。
  ルール（パラメータは文献の定番値で固定し、最適化しない）
    MPI(ver4.0)      : MACD(12,26,9) と パラボリック(0.02,0.02,0.2) の記事条件
    MACDのみ         : MACD > シグナル なら保有
    パラボリックのみ : 終値 > パラボリック なら保有
    10か月線         : 終値 > 10か月単純移動平均 なら保有（Faber 2007 の定番）
    12か月線         : 終値 > 12か月単純移動平均 なら保有
    12か月モメンタム : 終値 > 12か月前の終値 なら保有（時系列モメンタム）
    参考: 3倍保有（初日に3倍を買って持ち続ける）、1倍保有
  検証セット: oos.py の SETS と同じ7つ。ただし NDX(IS) は全ルールの準備期間がそろう 1989/1 開始（MPIの初回買いは1989/4）。
  頑健性: 月足の締め日21通り（k=-10〜+10、perturb.py と同じ）で全ルールを計算し、分布で比べる。
          さらに締め日k=0で10年窓（毎年1月開始の一括投資）も計算。
  判定（事前固定）: MPIの21通り中央値が「10か月線」「12か月線」の両方の中央値を、ISと OOS 6セット中4セット以上で上回れば
          「MACD＋パラボリックの複雑さに意味あり」。満たさなければ「単純ルールで足りる」。
"""
import sys
sys.path.insert(0, ".")
from perturb import *

INITIAL = 1_000_000.0
MODES = {"一括100万": 0.0, "一括100万+月3万": 30000.0}
RULES = ["MPI(ver4.0)", "MACDのみ", "パラボリックのみ", "10か月線", "12か月線", "12か月モメンタム"]
BENCH = {"3倍保有": "dca3", "1倍保有": "dca1"}
SETS2 = [(l, k, ix, ("1989-01" if l.startswith("NDX 1985") else st), en) for l, k, ix, st, en in SETS]
SETS2[0] = ("NDX 1989-2026", SETS2[0][1], "NDX", "1989-01", "2026-10")


def state_events(bars: pd.DataFrame, state: np.ndarray) -> pd.DataFrame:
    """保有状態(1/0/NaN=未確定)の列 → 売買シグナル(+1/-1)。状態が変わった足で発生"""
    out = np.zeros(len(bars), dtype=int)
    prev = 0
    for i, s in enumerate(state):
        if np.isnan(s):
            continue
        s = int(s)
        if s != prev:
            out[i] = 1 if s == 1 else -1
            prev = s
    r = bars.copy(); r["sig"] = out
    return r


def rule_signals(bars: pd.DataFrame, rule: str) -> pd.DataFrame:
    c = bars.c.values
    if rule == "MPI(ver4.0)":
        return signals(bars)
    if rule == "MACDのみ":
        macd = pine_ema(c, 12) - pine_ema(c, 26); sg = pine_ema(macd, 9)
        st = np.where(np.isnan(sg), np.nan, (macd > sg).astype(float))
    elif rule == "パラボリックのみ":
        ps = pine_sar(bars.h.values, bars.l.values, c, 0.02, 0.02, 0.2)
        st = np.where(np.isnan(ps), np.nan, (c > ps).astype(float))
    elif rule in ("10か月線", "12か月線"):
        n = 10 if rule == "10か月線" else 12
        sma = pd.Series(c).rolling(n).mean().values
        st = np.where(np.isnan(sma), np.nan, (c > sma).astype(float))
    elif rule == "12か月モメンタム":
        lag = pd.Series(c).shift(12).values
        st = np.where(np.isnan(lag), np.nan, (c > lag).astype(float))
    else:
        raise ValueError(rule)
    return state_events(bars, st)


def init_regime(sig: pd.DataFrame, start: str) -> str:
    """開始日より前に締まった足の最後のシグナルで開始時の状態を決める"""
    s = sig[(sig.sig != 0) & (sig.last_day < pd.Timestamp(start + "-01"))]
    return "long" if len(s) and s.sig.iloc[-1] == 1 else "out"


def run_rule(daily, sig, cfg):
    cfg = replace(cfg, init_regime=init_regime(sig, cfg.start))
    r, h, t = run(daily, DUMMY, cfg, exec_dates=exec_of(sig))
    return r, h


def pack(r):
    return dict(final=r["final_after_liq"], contrib=r["contrib"], irr=r["irr"], mdd=r["mdd_twr"], trades=r["n_trades"])


def main():
    D = datasets()
    cost = {}
    for k, (e3, e2) in CAL.items():
        cost[k] = (calibrate_cost(D[k], e3, 3)[0], calibrate_cost(D[k], e2, 2)[0])
    cost["IXIC"] = cost["NDX"]
    SIG = {}
    for ix, d in D.items():
        for k in KS:
            b = shifted_bars(d, k)
            for ru in RULES:
                SIG[(ix, k, ru)] = rule_signals(b, ru)
    rows, win_rows, paths = [], [], {}
    for lab, kind, ix, st, en in SETS2:
        for mode, mon in MODES.items():
            C = replace(base_cfg(*cost[ix]), start=st, end=en, initial=INITIAL, monthly=mon)
            for ru in RULES:
                for k in KS:
                    r, h = run_rule(D[ix], SIG[(ix, k, ru)], C)
                    rows.append(dict(set=lab, kind=kind, idx=ix, mode=mode, rule=ru, k=k,
                                     init=init_regime(SIG[(ix, k, ru)], st), **pack(r)))
                    if mode == "一括100万" and k == 0 and lab.startswith("NDX 1989"):
                        paths[ru] = h.value_jpy.resample("ME").last()
            for bn, strat in BENCH.items():
                r, h, _ = run(D[ix], DUMMY, replace(C, strategy=strat))
                rows.append(dict(set=lab, kind=kind, idx=ix, mode=mode, rule=bn, k=0, init="-", **pack(r)))
                if mode == "一括100万" and lab.startswith("NDX 1989"):
                    paths[bn] = h.value_jpy.resample("ME").last()
        # 10年窓（一括100万、締め日k=0）
        C = replace(base_cfg(*cost[ix]), initial=INITIAL, monthly=0.0)
        for a, b in windows(st, en):
            Cw = replace(C, start=a, end=b)
            for ru in RULES:
                r, _ = run_rule(D[ix], SIG[(ix, 0, ru)], Cw)
                win_rows.append(dict(set=lab, kind=kind, rule=ru, start=a, end=b, **pack(r)))
            for bn, strat in BENCH.items():
                r, _, _ = run(D[ix], DUMMY, replace(Cw, strategy=strat))
                win_rows.append(dict(set=lab, kind=kind, rule=bn, start=a, end=b, **pack(r)))
        print(lab, "done", flush=True)
    pd.to_pickle(dict(res=pd.DataFrame(rows), win=pd.DataFrame(win_rows), paths=paths, cost=cost,
                      sig={k: v for k, v in SIG.items() if k[0] == "NDX" and k[1] == 0}), "data/simple_rules.pkl")


if __name__ == "__main__":
    main()
