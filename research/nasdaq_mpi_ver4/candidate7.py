"""次の候補7: 12か月線で「売った後の資金の置き場」と「高金利時の2倍切替」を組み合わせ、保険料をどこまで下げられるか（100万円一括）

設計（結果を見る前に固定）
  シグナル: 12か月線（終値 > 12か月平均なら保有）。締め日21通り(k=-10〜+10)。7セット（simple_rules.py と同じ）。
  資金: 主=100万円一括・積立なし、感応度=100万円+月3万円。コスト: 現実コストC、締め日の翌営業日の引けで約定。
  置き場（売った後）:
    drip = 現金→毎月1%ずつ1倍（ver4.0 と同じ。基準）
    cash = 全額USD現金（金利0）
    mmf  = 全額 米ドルMMF（米3M金利 − 年0.3%、分配は毎日20.315%課税、損益通算なしの保守的な扱い）
    one  = 全額すぐ1倍（NDX等の1倍ETF）
  レバ: 3倍固定 / ①6%超→2倍（毎月判定、前回のOOS検証でISから選んだ規則をそのまま使う）
  判定（事前固定）
    手順1 置き場: drip と比べ、21通り中央値がIS と OOS 6セット中4以上で上回れば「改善」。複数なら勝ちセット数→IS中央値の順で1つ選ぶ。
    手順2 2倍切替: 手順1の置き場で、3倍固定と比べて同じ基準。
    保険料: 最終の組合せの中央値 ÷ 3倍保有（1未満なら、その差が全損回避のために払った保険料）。
"""
import sys
sys.path.insert(0, ".")
from simple_rules import *

EXITS = ["drip", "cash", "mmf", "one"]
EXN = {"drip": "現金→毎月1%ずつ1倍(基準)", "cash": "全額現金(金利0)", "mmf": "全額 米ドルMMF", "one": "全額すぐ1倍"}
LEVS = {"3倍固定": {}, "6%超→2倍": dict(rate_thr=0.06, rate_mode="monthly")}
RULE = "12か月線"


def main():
    D = datasets()
    cost = {}
    for k, (e3, e2) in CAL.items():
        cost[k] = (calibrate_cost(D[k], e3, 3)[0], calibrate_cost(D[k], e2, 2)[0])
    cost["IXIC"] = cost["NDX"]
    SIG = {(ix, k): rule_signals(shifted_bars(D[ix], k), RULE) for ix in D for k in KS}
    rows = []
    for lab, kind, ix, st, en in SETS2:
        for mode, mon in MODES.items():
            C = replace(base_cfg(*cost[ix]), start=st, end=en, initial=INITIAL, monthly=mon)
            for ex in EXITS:
                for ln, kw in LEVS.items():
                    for k in KS:
                        r, h = run_rule(D[ix], SIG[(ix, k)], replace(C, exit_mode=ex, **kw))
                        rows.append(dict(set=lab, kind=kind, idx=ix, mode=mode, exit=ex, lev=ln, k=k,
                                         n_switch=r["n_switch"], share2=r["share_2x"], **pack(r)))
        print(lab, "done", flush=True)
    pd.to_pickle(dict(res=pd.DataFrame(rows), cost=cost, sig={k: SIG[("NDX", k)] for k in [0]}), "data/candidate7.pkl")


if __name__ == "__main__":
    main()
