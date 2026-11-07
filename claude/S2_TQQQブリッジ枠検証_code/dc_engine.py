"""
DC規則の一斉比較 ③ のエンジン（事前登録 dc_prereg.py ＋追記1〜5 のとおり）
-------------------------------------------------------------------------
・DCの投信は実際の基準価額（data_dc/、25本）。設定前は代用でつなぐ（010←先進国株、006←日本株、012←外国債券、008←国内債券、037←新興国株）
・暦は日本の営業日（023の日付）。月末に判定→翌営業日に売却→遅延（基準4営業日）後に購入、その間は現金0%
・預金（019）：持ち続けた月数が6か月未満は0%、6か月以上は年 rate（日割り）
"""
from __future__ import annotations
import sys, math
sys.path.insert(0, ".")
import numpy as np, pandas as pd
import hh, s2engine as E

DCDIR = "data_dc"
CODES = ["001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011", "012", "020", "021", "022", "023",
         "025", "026", "030", "031", "033", "034", "035", "036", "037"]
PROXY = {"010": "DEV", "006": "JP", "012": "FBOND", "008": "DBOND", "037": "EM"}   # 事前登録どおり
STOCKS_R10 = ["006", "004", "005", "022", "023", "034", "009", "010", "035", "036", "037"]
END = "2026-10-31"
YDAYS = 245.0                      # 日本の営業日（年）


class DCWorld:
    def __init__(self, data="data"):
        idx = pd.read_csv(f"{DCDIR}/index.csv", dtype=str)
        self.files = {r["番号"]: r["ファイル"] for _, r in idx.iterrows()}
        self.nav = {c: pd.read_csv(f"{DCDIR}/{self.files[c]}", parse_dates=["date"], index_col="date")["nav"].astype(float)
                    for c in CODES}
        self.mkt = hh.load_all(data)
        self.A = hh.asset_returns(self.mkt)
        self.judg = E.judge_states(self.mkt)
        cal = self.nav["023"].index
        self.cal = cal[(cal >= "2000-01-01") & (cal <= END)]
        cal = self.cal
        R, REAL = {}, {}
        for c in CODES:
            s = self.nav[c]
            first = s.index[0]
            px = s.reindex(cal.union(s.index)).ffill().reindex(cal)
            r = px.pct_change()
            real = pd.Series(cal > first, index=cal) & px.shift(1).notna()
            r = r.where(real)
            if c in PROXY:
                pcum = (1 + self.A[PROXY[c]]).cumprod()
                pp = pcum.reindex(cal.union(pcum.index)).ffill().reindex(cal)
                pr = pp.pct_change()
                r = r.where(real, pr)
            R[c] = r
            REAL[c] = real
        self.R = pd.DataFrame(R)                     # 日次リターン（つないだもの。代用のない投信は設定前NaN）
        self.REAL = pd.DataFrame(REAL)               # 実データの日
        # 月末（日本の最終営業日）
        s = pd.Series(cal, index=cal)
        self.me = pd.DatetimeIndex(s.groupby([cal.year, cal.month]).last().values)
        self.me_pos = {d: i for i, d in enumerate(cal) if d in set(self.me)}
        pxa = pd.DataFrame({c: self._px_series(c) for c in CODES})
        self.pme = pxa.loc[self.me]                  # 月末の価格（つないだもの）
        realpx = pd.DataFrame({c: self.nav[c].reindex(cal.union(self.nav[c].index)).ffill().reindex(cal)
                               .where(self.REAL[c] | (cal == self.nav[c].index[0])) for c in CODES})
        self.rme = realpx.loc[self.me]               # 月末の実際の基準価額（設定前はNaN）
        st = self.judg["state"]
        # 各月の米国の最終営業日の判定（同じ月の最後の判定）
        stp = pd.Series(st.values, index=st.index.to_period("M"))
        stp = stp.groupby(level=0).last()
        self.state = pd.Series([stp.get(d.to_period("M"), None) for d in self.me], index=self.me)
        # 010の直近3ヶ月の年率ボラ（日次、日本の暦）
        r010 = self.R["010"]
        self.vol3 = pd.Series([r010[(r010.index > d - pd.DateOffset(months=3)) & (r010.index <= d)].std() * math.sqrt(YDAYS)
                               for d in self.me], index=self.me)

    def _px_series(self, c):
        r = self.R[c]
        ok = r.notna()
        if not ok.any():
            return pd.Series(np.nan, index=r.index)
        f = ok.idxmax()
        out = pd.Series(np.nan, index=r.index)
        seg = r[r.index >= f].fillna(0.0)
        out[r.index >= f] = (1 + seg).cumprod().values
        # 開始日の前日を1とする基準（開始日のリターンを含む）
        return out


# =============================================================
# 規則（月末kの情報 → 目標比率）
# =============================================================
def _on(st):
    return st in ("NORMAL", "DIP")


def _ret12(w: DCWorld, k, codes, real_only=()):
    out = {}
    for c in codes:
        tab = w.rme if c in real_only else w.pme
        if k < 12:
            continue
        a, b = tab[c].iloc[k], tab[c].iloc[k - 12]
        if a == a and b == b and b > 0:
            out[c] = a / b - 1
    return out


def _above(w: DCWorld, k, c, n):
    if k < n - 1:
        return None
    x = w.pme[c].iloc[k - n + 1:k + 1]
    if x.isna().any():
        return None
    return w.pme[c].iloc[k] > x.mean()


DEP = "DEP"


def r0(w, k):
    return {"010": 1.0} if _on(w.state.iloc[k]) else {DEP: 1.0}


def r1(w, k):
    return {"010": 1.0}


def r2(w, k):
    return {"003": 1.0}


def r3(w, k):
    a = _above(w, k, "010", 10)
    return {"010": 1.0} if (a is None or a) else {DEP: 1.0}


def _r45(w, k, bond):
    if _on(w.state.iloc[k]):
        return {"010": 1.0}
    a = _above(w, k, bond, 12)
    return {bond: 1.0} if a else {DEP: 1.0}


def r4(w, k):
    return _r45(w, k, "012")


def r5(w, k):
    return _r45(w, k, "008")


def r6(w, k):
    m = _ret12(w, k, ["006", "010", "037"])
    if not m:
        return {"010": 1.0}
    b = max(m, key=m.get)
    return {b: 1.0} if m[b] > 0 else {DEP: 1.0}


def r7(w, k):
    m = _ret12(w, k, ["006", "010", "037", "026", "012", "008"], real_only=("026",))
    if not m:
        return {"010": 1.0}
    b = max(m, key=m.get)
    return {b: 1.0} if m[b] > 0 else {DEP: 1.0}


def r8(w, k):
    return {"010": .70, "037": .15, "006": .15} if _on(w.state.iloc[k]) else {DEP: 1.0}


def r9(w, k):
    if not _on(w.state.iloc[k]):
        return {DEP: 1.0}
    v = w.vol3.iloc[k]
    x = 1.0 if not (v == v) or v <= 0 else min(1.0, 0.15 / v)
    return {"010": x, DEP: 1 - x} if x < 1 else {"010": 1.0}


def r10(w, k):
    if not _on(w.state.iloc[k]):
        return {DEP: 1.0}
    m = _ret12(w, k, STOCKS_R10, real_only=tuple(STOCKS_R10))
    if not m:
        return {"010": 1.0}
    return {max(m, key=m.get): 1.0}


def r11(w, k):
    a = _above(w, k, "010", 10)
    return {"010": 1.0} if (_on(w.state.iloc[k]) and (a is None or a)) else {DEP: 1.0}


RULES = {
    "R0": ("DC④（現状）：○は010、×は預金", r0, ["010"]),
    "R1": ("010を持ちっぱなし", r1, ["010"]),
    "R2": ("003マイストーリー75を持ちっぱなし", r2, ["003"]),
    "R3": ("010の10ヶ月線", r3, ["010"]),
    "R4": ("DC④＋×は012外国債券（12ヶ月平均の上なら）", r4, ["010", "012"]),
    "R5": ("DC④＋×は008国内債券（12ヶ月平均の上なら）", r5, ["010", "008"]),
    "R6": ("デュアル・モメンタム（株3本）", r6, ["006", "010", "037"]),
    "R7": ("デュアル・モメンタム（株＋債券＋REIT）", r7, ["006", "010", "037", "012", "008"]),
    "R8": ("DC④で○は010 70%＋037 15%＋006 15%", r8, ["010", "037", "006"]),
    "R9": ("ボラ連動（○は010をσ15%目標）", r9, ["010"]),
    "R10": ("DC④で○は株の投信の12ヶ月勝者", r10, ["010"]),
    "R11": ("二重確認（DC④とR3の両方○のときだけ010）", r11, ["010"]),
}
ORDER = list(RULES)


# =============================================================
# 日次の実行
# =============================================================
def run_rule(w: DCWorld, rule, start="2000-04-01", delay=4, rate=0.001, dep_model="019", band=0.05, end=END):
    """
    dep_model: "019"＝6か月未満0%・以後 rate、"flat"＝ずっと rate、"018"＝6か月未満0%・以後 rate（呼び出し側で0.35%を渡す）
    返り値 dict(nav=日次NAV, hold=日次の目標, nsw=スイッチ回数, dep_share=預金比率の平均)
    """
    fn = rule[1] if isinstance(rule, tuple) else rule
    cal = w.cal
    i0 = int(cal.searchsorted(pd.Timestamp(start)))
    i1 = int(cal.searchsorted(pd.Timestamp(end), side="right"))
    need = rule[2] if isinstance(rule, tuple) else ["010"]
    # 必ず持つ投信が揃う日から（R2の003など）
    first_ok = max(int(np.argmax(w.R[c].notna().values)) for c in need)
    i0 = max(i0, first_ok)
    me_idx = [w.me_pos[d] for d in w.me]
    me_k = {p: k for k, p in enumerate(me_idx)}
    cols = list(w.R.columns)
    cpos = {c: j for j, c in enumerate(cols)}
    Rv = w.R.values
    nA = len(cols)
    D = nA                                         # 預金の位置
    vals = np.zeros(nA + 1)
    # 初期：直前の月末の目標をそのまま持つ
    kprev = max(k for k, p in enumerate(me_idx) if p < i0)
    tgt0 = fn(w, kprev)
    for a, x in tgt0.items():
        vals[cpos[a] if a != DEP else D] = x
    cash = 0.0
    dep_m = 0
    sell_i = buy_i = None
    tgt = None
    nav = np.zeros(i1 - i0)
    depw = np.zeros(i1 - i0)
    nsw = 0
    dd_rate = (1 + rate) ** (1 / YDAYS) - 1
    for i in range(i0, i1):
        # 1) その日のリターン
        held = np.nonzero(vals[:nA] > 0)[0]
        for j in held:
            rv = Rv[i, j]
            if rv != rv:
                raise ValueError(f"NaN return {cols[j]} {cal[i].date()}")
            vals[j] *= 1 + rv
        if vals[D] > 0:
            if dep_model == "flat" or dep_m >= 6:
                vals[D] *= 1 + dd_rate
        # 2) 売却（申込日）
        if sell_i is not None and i == sell_i:
            tot = vals.sum() + cash
            want = np.zeros(nA + 1)
            for a, x in tgt.items():
                want[cpos[a] if a != DEP else D] = x * tot
            ex = np.maximum(vals - want, 0.0)
            vals -= ex
            cash += ex.sum()
            if vals[D] <= 1e-12:
                dep_m = 0
            nsw += 1
        # 3) 購入の約定
        if buy_i is not None and i == buy_i:
            tot = vals.sum() + cash
            want = np.zeros(nA + 1)
            for a, x in tgt.items():
                want[cpos[a] if a != DEP else D] = x * tot
            de = np.maximum(want - vals, 0.0)
            if de.sum() > 0:
                vals += de * (cash / de.sum())
            else:
                vals[D] += cash
            cash = 0.0
            sell_i = buy_i = None
        tot = vals.sum() + cash
        nav[i - i0] = tot
        depw[i - i0] = vals[D] / tot
        # 4) 月末の判定
        if i in me_k:
            k = me_k[i]
            if vals[D] > 1e-12 and i > i0:
                dep_m += 1
            if sell_i is not None or i + 1 >= i1:
                continue
            t = fn(w, k)
            cur = {(cols[j] if j < nA else DEP): vals[j] / tot for j in np.nonzero(vals > 1e-12)[0]}
            if set(t) == set(cur) and max(abs(t[a] - cur[a]) for a in t) <= band:
                continue
            tgt = t
            sell_i = i + 1
            buy_i = min(i + 1 + delay, i1 - 1)
    nv = pd.Series(nav, index=cal[i0:i1])
    return dict(nav=nv, nsw=nsw, dep_share=float(depw.mean()))


def monthly(nav):
    return nav.resample("ME").last().pct_change().dropna()


def real_start(w: DCWorld, key):
    """DC単体の「実データの期間」の開始（規則が必ず持つ投信の実データが揃う日）。"""
    need = RULES[key][2]
    return max(w.nav[c].index[0] for c in need)
