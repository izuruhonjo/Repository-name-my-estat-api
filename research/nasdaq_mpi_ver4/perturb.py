"""シグナル摂動テスト: ver4.0 の結果が「月足の締め日」と「少数のシグナル」にどれだけ依存しているか

設計（結果を見る前に固定）
  共通: 現実コストC（SBI手数料・為替・日本税制・較正コスト）、名目3万円/月、積立は月初、シグナルは締め日の翌営業日引けで約定。
        積立日・コスト・税は一切変えず、シグナルだけを動かす。
  P1 締め日シフト: 月足の締め日を「月末最終営業日 + k 営業日」にずらして、全期間の月足・MACD・パラボリックを作り直す。
        k = -10〜+10 の21通り（≒1か月の全位相）。k=0 が基準（=ケースC 38.0億円）。
        追加: 暦日締め（5/10/15/20/25日締め＝その日以前の最終営業日）。
  P2 約定遅延: シグナルは基準のまま、約定を締め日の d 営業日後に（d=0〜5。d=1が基準。d=0は厳密には実行不能）。
  P3 エピソード除去: 基準の連続する2シグナル（買→売 = 1回の保有期間、売→買 = 1回の退避期間）を1組ずつ消す。
        「その1回の退避／保有がなかったら」の最終資産の変化で、各シグナルの寄与を測る。
  対象: P1・P2 は IS(NDX 1985/10〜2026/10) と OOS 6セット（oos.py の SETS と同一）。P3 は NDX(IS) のみ。

判定基準（事前固定）
  A 位相頑健性: P1の21通りの中央値 ÷ 基準(k=0)。≥0.5 頑健 / 0.25〜0.5 中程度 / <0.25 脆弱（基準が上振れした「当たり位相」）
  B 対ベンチマーク: P1の21通りのうち 3倍単純積立・1倍単純積立 に勝つ割合（80%以上で「締め日に依らず優位」）
  C 集中度: P3で1組除去しただけで最終資産が半分以下（Δlog ≤ −ln2）になる組があれば「単一シグナル依存」
"""
import sys
sys.path.insert(0, ".")
from oos import *

KS = list(range(-10, 11))
CAL_DAYS = [5, 10, 15, 20, 25]
LAGS = [0, 1, 2, 3, 4, 5]
END = "2026-10"


def bars_from_ends(daily: pd.DataFrame, ends: np.ndarray, labels) -> pd.DataFrame:
    """締め日の位置 ends（daily の行番号, 昇順）で月足を作る。bar j = (ends[j-1], ends[j]]"""
    o, h, l, c = daily.o.values, daily.h.values, daily.l.values, daily.c.values
    rows, prev = [], -1
    for e in ends:
        s = prev + 1
        rows.append((o[s], h[s:e + 1].max(), l[s:e + 1].min(), c[e], daily.index[e]))
        prev = e
    return pd.DataFrame(rows, columns=["o", "h", "l", "c", "last_day"], index=pd.PeriodIndex(labels, freq="M"))


def month_end_pos(daily: pd.DataFrame, end=END):
    per = daily.index.to_period("M")
    pos = np.where(np.r_[per[1:] != per[:-1], True])[0]
    lab = per[pos]
    keep = lab <= pd.Period(end, "M")
    return pos[keep], lab[keep]


def shifted_bars(daily: pd.DataFrame, k: int, end=END) -> pd.DataFrame:
    """締め日 = 各月の最終営業日 + k 営業日（ラベルは元の月）。データ末尾を超える足は捨てる"""
    pos, lab = month_end_pos(daily, end)
    e = pos + k
    ok = (e >= 0) & (e < len(daily))
    return bars_from_ends(daily, e[ok], lab[ok])


def calendar_bars(daily: pd.DataFrame, day: int, end=END) -> pd.DataFrame:
    """暦日締め: 各月の day 日以前の最終営業日で締める"""
    idx = daily.index
    per = idx.to_period("M")
    ends, labs = [], []
    for p in per.unique():
        if p > pd.Period(end, "M"):
            break
        m = np.where((per == p) & (idx.day <= day))[0]
        if len(m):
            ends.append(m[-1]); labs.append(p)
    return bars_from_ends(daily, np.array(ends), labs)


def exec_of(sig: pd.DataFrame) -> dict:
    s = sig[sig.sig != 0]
    return {r.last_day: int(r.sig) for _, r in s.iterrows()}


DUMMY = pd.DataFrame({"sig": [0], "last_day": [pd.Timestamp("1900-01-31")]}, index=pd.PeriodIndex(["1900-01"], freq="M"))


def one(daily, cfg, ex):
    r, h, t = run(daily, DUMMY, cfg, exec_dates=ex)   # exec_dates を渡すと sig は使われない
    return dict(final=r["final_after_liq"], contrib=r["contrib"], irr=r["irr"], mdd=r["mdd_twr"], trades=r["n_trades"])


def in_period(ex: dict, daily, cfg):
    """期間内で実際に約定するシグナル（run の exec_map と同じ規則）を時系列で"""
    d = daily.loc[cfg.start: (pd.Period(cfg.end, "M") + 1).start_time - pd.Timedelta(days=1)]
    dates = d.index
    out = []
    for dte in sorted(ex):
        pos = dates.searchsorted(dte)
        if pos < len(dates) and dates[pos] == dte and pos + cfg.exec_lag < len(dates):
            out.append((dte, ex[dte]))
    # run() は regime と一致しないシグナルを無視するので、実効シグナル列に揃える
    eff, regime = [], "out"
    for dte, s in out:
        if s == 1 and regime == "out":
            eff.append((dte, s)); regime = "long"
        elif s == -1 and regime == "long":
            eff.append((dte, s)); regime = "out"
    return eff


def main():
    D = datasets()
    cost = {}
    for k, (e3, e2) in CAL.items():
        cost[k] = (calibrate_cost(D[k], e3, 3)[0], calibrate_cost(D[k], e2, 2)[0])
    cost["IXIC"] = cost["NDX"]
    BARS, SIGS = {}, {}
    for ix, d in D.items():
        for k in KS:
            b = shifted_bars(d, k); BARS[(ix, f"k{k:+d}")] = b; SIGS[(ix, f"k{k:+d}")] = signals(b)
        for day in CAL_DAYS:
            b = calendar_bars(d, day); BARS[(ix, f"d{day}")] = b; SIGS[(ix, f"d{day}")] = signals(b)
        # 回帰: k=0 は既存の monthly_bars と完全一致すること
        m0 = monthly_bars(d).loc[:END]
        b0 = BARS[(ix, "k+0")]
        assert np.array_equal(m0[["o", "h", "l", "c"]].values, b0[["o", "h", "l", "c"]].values), ix
        assert (signals(m0).sig.values == SIGS[(ix, "k+0")].sig.values).all(), ix
    rows = []
    for lab, kind, ix, st, en in SETS:
        C = replace(base_cfg(*cost[ix]), start=st, end=en)
        for key in [f"k{k:+d}" for k in KS] + [f"d{x}" for x in CAL_DAYS]:
            ex = exec_of(SIGS[(ix, key)])
            rows.append(dict(set=lab, kind=kind, idx=ix, test="P1締め日", var=key, n_sig=len(in_period(ex, D[ix], C)),
                             **one(D[ix], C, ex)))
        ex0 = exec_of(SIGS[(ix, "k+0")])
        for lag in LAGS:
            rows.append(dict(set=lab, kind=kind, idx=ix, test="P2約定遅延", var=f"lag{lag}", n_sig=len(in_period(ex0, D[ix], C)),
                             **one(D[ix], replace(C, exec_lag=lag), ex0)))
        for dv, nm in [("dca1", "1倍単純積立"), ("dca3", "3倍単純積立")]:
            r, _, _ = run(D[ix], SIGS[(ix, "k+0")], replace(C, strategy=dv))
            rows.append(dict(set=lab, kind=kind, idx=ix, test="参考", var=nm, n_sig=0, final=r["final_after_liq"],
                             contrib=r["contrib"], irr=r["irr"], mdd=r["mdd_twr"], trades=0))
        print(lab, "done", flush=True)
    res = pd.DataFrame(rows)

    # P3 エピソード除去（NDX IS）
    lab, kind, ix, st, en = SETS[0]
    C = replace(base_cfg(*cost[ix]), start=st, end=en)
    ex0 = exec_of(SIGS[(ix, "k+0")])
    eff = in_period(ex0, D[ix], C)
    base = one(D[ix], C, dict(eff))["final"]
    ep = []
    for i in range(len(eff) - 1):
        a, b = eff[i], eff[i + 1]
        ex = dict(eff); ex.pop(a[0]); ex.pop(b[0])
        r = one(D[ix], C, ex)
        ep.append(dict(i=i, d1=a[0], s1=a[1], d2=b[0], s2=b[1],
                       kind="退避を消す(保有継続)" if a[1] == -1 else "保有を消す(退避継続)",
                       final=r["final"], dlog=np.log(r["final"] / base)))
    if len(eff) % 2 == 1:   # 最後の買い（2026/10時点で保有中）を単独で消す
        a = eff[-1]; ex = dict(eff); ex.pop(a[0]); r = one(D[ix], C, ex)
        ep.append(dict(i=len(eff) - 1, d1=a[0], s1=a[1], d2=pd.NaT, s2=0, kind="最後の買いを消す",
                       final=r["final"], dlog=np.log(r["final"] / base)))
    ep = pd.DataFrame(ep)

    # P1 各位相のシグナル日（ドットコム期の売りの日付などを確認するため）
    sigtab = []
    for key in [f"k{k:+d}" for k in KS] + [f"d{x}" for x in CAL_DAYS]:
        C = replace(base_cfg(*cost["NDX"]), start="1985-10", end=END)
        for dte, s in in_period(exec_of(SIGS[("NDX", key)]), D["NDX"], C):
            sigtab.append(dict(var=key, date=dte, sig=s))
    pd.to_pickle(dict(res=res, ep=ep, eff=eff, base=base, cost=cost, sigtab=pd.DataFrame(sigtab),
                      bars={k: v for k, v in BARS.items() if k[0] == "NDX"},
                      sigs={k: v for k, v in SIGS.items() if k[0] == "NDX"}), "data/perturb.pkl")
    for k in D:
        D[k].to_pickle(f"data/daily_{k}.pkl")
    return res


if __name__ == "__main__":
    main()
