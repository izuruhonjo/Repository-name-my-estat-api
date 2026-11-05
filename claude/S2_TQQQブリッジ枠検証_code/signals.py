"""
ブリッジ枠の買いシグナル群（日次、QQQ米ドル終値で計算）
A 売られすぎ / B 恐怖ピーク越え（VXN代替：実現ボラ）/ C 信用不安ピーク越え（LQD/HYG対IEF比）
D 反転の確認 / E ボラの山越え / テクニカル各種（MACD・パラボリック・移動平均・BB・RSI・ドンチャン・コポック）
F 組み合わせ（2条件まで）
すべて「True の日の翌営業日に買う」形。先読みなし（当日終値までの情報のみ）。
"""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(close, fast=12, slow=26, sig=9):
    m = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    s = m.ewm(span=sig, adjust=False).mean()
    return m, s, m - s


def parabolic_sar(high, low, close, af0=0.02, af_max=0.2):
    """Wilder のパラボリックSAR。返り値：SAR値と bullish フラグ（終値>SAR）。"""
    n = len(close)
    sar = np.zeros(n)
    bull = np.zeros(n, dtype=bool)
    h, l, c = high.values, low.values, close.values
    up = True
    af = af0
    ep = h[0]
    sar[0] = l[0]
    for i in range(1, n):
        prev = sar[i - 1]
        if up:
            s = prev + af * (ep - prev)
            s = min(s, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < s:
                up = False
                s = ep
                ep = l[i]
                af = af0
            else:
                if h[i] > ep:
                    ep = h[i]
                    af = min(af + af0, af_max)
        else:
            s = prev + af * (ep - prev)
            s = max(s, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > s:
                up = True
                s = ep
                ep = h[i]
                af = af0
            else:
                if l[i] < ep:
                    ep = l[i]
                    af = min(af + af0, af_max)
        sar[i] = s
        bull[i] = up
    return pd.Series(sar, index=close.index), pd.Series(bull, index=close.index)


def realized_vol(close, n=20):
    return np.log(close).diff().rolling(n).std() * np.sqrt(252)


def cross_up(a: pd.Series, b) -> pd.Series:
    """a が b を下から上に抜けた日。"""
    if np.isscalar(b):
        return (a > b) & (a.shift(1) <= b)
    return (a > b) & (a.shift(1) <= b.shift(1))


def build_signals(mkt: pd.DataFrame, ohlc: pd.DataFrame | None = None) -> dict[str, pd.Series]:
    """返り値：名前 -> bool Series（QQQ取引日）。ohlc は QQQ の high/low（SAR用）。"""
    c = mkt["qqq"]
    idx = c.index
    S = {}
    dd252 = c / c.rolling(252).max() - 1
    rv = realized_vol(c)
    r2, r14 = rsi(c, 2), rsi(c, 14)
    sma = {n: c.rolling(n).mean() for n in (10, 20, 50, 100, 200)}
    ema = {n: c.ewm(span=n, adjust=False).mean() for n in (10, 20, 50)}

    # --- A 売られすぎ（過剰反応） ---
    S["A1_dd30_rsi2<10"] = (dd252 <= -0.30) & (r2 < 10)
    S["A2_dd25_rsi14<30"] = (dd252 <= -0.25) & (r14 < 30)
    S["A3_rsi14_cross30"] = cross_up(r14, 30)                      # RSI14が30を上抜け
    S["A4_rsi2_cross10"] = cross_up(r2, 10)
    S["A5_dd35_any"] = (dd252 <= -0.35)                             # 高値から35%下（単純）

    # --- B 恐怖のピーク越え（VXNの代替として実現ボラ） ---
    rv_peak = rv.rolling(60).max()
    S["B1_rv_peak>40_fall1/3"] = (rv_peak >= 0.40) & (rv <= rv_peak * 2 / 3) & (rv.shift(1) > rv_peak.shift(1) * 2 / 3)
    S["B2_rv_peak>50_fall1/2"] = (rv_peak >= 0.50) & (rv <= rv_peak * 0.5) & (rv.shift(1) > rv_peak.shift(1) * 0.5)

    # --- C 信用不安のピーク越え（LQD/IEF, HYG/IEF 比率が1年安値をつけて反転） ---
    for nm in ("lqd", "hyg"):
        if nm in mkt and mkt[nm].notna().any():
            ratio = (mkt[nm] / mkt["ief"]).dropna()
            lo = ratio.rolling(252).min()
            near_low = ratio <= lo.shift(1) * 1.02                     # 直近1年安値の2%以内
            turn = ratio > ratio.rolling(20).mean()
            s = (near_low.shift(5).rolling(20).max() > 0) & cross_up(ratio, ratio.rolling(20).mean())
            S[f"C_{nm}_ief_turn"] = s.reindex(idx).fillna(False)

    # --- D 反転の確認 ---
    S["D1_close_cross_sma50"] = cross_up(c, sma[50])
    S["D2_low+10%"] = cross_up(c / c.rolling(60).min() - 1, 0.10)
    S["D3_low+15%"] = cross_up(c / c.rolling(60).min() - 1, 0.15)
    S["D4_10d_gain>8%"] = cross_up(c / c.shift(10) - 1, 0.08)        # Zweig型の急反発
    S["D5_close_cross_sma200"] = cross_up(c, sma[200])
    S["D6_close_cross_ema20"] = cross_up(c, ema[20])

    # --- E ボラの山越え（既存ボラ・ブレーキの計算を流用） ---
    rv_peak30 = rv.where(rv >= 0.30).rolling(120, min_periods=1).max()
    S["E1_rv30_peak_fall1/3"] = (rv_peak30 >= 0.30) & (rv <= rv_peak30 * 2 / 3) & (rv.shift(1) > rv_peak30.shift(1) * 2 / 3)
    S["E2_rv_cross_down30"] = (rv < 0.30) & (rv.shift(1) >= 0.30)
    S["E3_rv_cross_down25"] = (rv < 0.25) & (rv.shift(1) >= 0.25) & (rv.rolling(60).max() >= 0.35)

    # --- テクニカル各種 ---
    m, s_, h = macd(c)
    S["T1_macd_cross_below0"] = cross_up(m, s_) & (m < 0)
    S["T2_macd_cross_any"] = cross_up(m, s_)
    S["T3_macd_hist_turn"] = (h > h.shift(1)) & (h.shift(1) < h.shift(2)) & (m < 0) & (h < 0)
    if ohlc is not None:
        sar, bull = parabolic_sar(ohlc["high"], ohlc["low"], c)
        S["T4_psar_flip_bull"] = bull & ~bull.shift(1).fillna(False).astype(bool)
    S["T5_sma10_cross_50"] = cross_up(sma[10], sma[50])
    S["T6_sma20_cross_100"] = cross_up(sma[20], sma[100])
    S["T7_golden_50_200"] = cross_up(sma[50], sma[200])
    S["T8_ema10_cross_50"] = cross_up(ema[10], ema[50])
    bb_mid = sma[20]
    bb_sd = c.rolling(20).std()
    S["T9_bb_lower_reentry"] = cross_up(c, bb_mid - 2 * bb_sd)
    S["T10_donchian20_break"] = c > c.rolling(20).max().shift(1)
    S["T11_donchian50_break"] = c > c.rolling(50).max().shift(1)
    # コポック曲線（月次版の日次近似：11ヶ月と14ヶ月のROCの合計の10期間加重移動平均）
    roc11 = c / c.shift(231) - 1
    roc14 = c / c.shift(294) - 1
    cop = (roc11 + roc14).rolling(210).apply(lambda x: np.dot(x, np.arange(1, 211)) / np.arange(1, 211).sum(), raw=True)
    S["T12_coppock_turn_up"] = (cop > cop.shift(1)) & (cop.shift(1) <= cop.shift(2)) & (cop < 0)
    # ストキャス
    lo14 = c.rolling(14).min(); hi14 = c.rolling(14).max()
    k = 100 * (c - lo14) / (hi14 - lo14)
    dline = k.rolling(3).mean()
    S["T13_stoch_cross20"] = cross_up(dline, 20)
    # 200日線からの乖離率が−20%以下から戻り
    dev200 = c / sma[200] - 1
    S["T14_dev200_-20_recover"] = cross_up(dev200, -0.15) & (dev200.rolling(40).min() <= -0.20)

    # --- F 組み合わせ（2条件：片方が過去20営業日内に成立＋もう片方が当日成立） ---
    def within(sig, n=20):
        return sig.astype(float).rolling(n, min_periods=1).max() > 0
    combos = [
        ("F1_dd30 & macd_cross", (dd252.rolling(20).min() <= -0.30), S["T2_macd_cross_any"]),
        ("F2_rvpeak & sma50", within(S["E1_rv30_peak_fall1/3"], 40), S["D1_close_cross_sma50"]),
        ("F3_rsi14<30 & low+10%", within(r14 < 30, 40), S["D2_low+10%"]),
        ("F4_dd30 & 10d_gain8", (dd252.rolling(20).min() <= -0.30), S["D4_10d_gain>8%"]),
        ("F5_bb_reentry & rv_fall", within(S["T9_bb_lower_reentry"], 20), S["E2_rv_cross_down30"]),
        ("F6_dd25 & psar", (dd252.rolling(20).min() <= -0.25), S.get("T4_psar_flip_bull", pd.Series(False, index=idx))),
        ("F7_dd30 & ema20", (dd252.rolling(20).min() <= -0.30), S["D6_close_cross_ema20"]),
    ]
    for nm, a, b in combos:
        S[nm] = (a & b).fillna(False)

    # 常時発動（×に入った翌日に即買い）：ベンチマーク用
    S["Z0_immediate"] = pd.Series(True, index=idx)

    return {k: v.reindex(idx).fillna(False).astype(bool) for k, v in S.items()}
