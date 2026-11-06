# 回帰テスト：拡張エンジン（既定・元エンジンと同じ癖）が s2engine.simulate と日次NAVで完全一致するか
import sys; sys.path.insert(0, '.')
import numpy as np, pandas as pd, s2engine as E, s2x as X
mkt = E.load_market("data"); assets = E.build_assets(mkt); judg = E.judge_states(mkt)
ok = True
for kw in [dict(), dict(start="2002-10-01"), dict(start="2007-10-01", exec_lag=3), dict(start="2013-01-01", slippage=0.005, exec_lag=5)]:
    a = E.simulate(mkt, assets, judg, E.Cfg(**kw))
    b = X.simulate_x(mkt, assets, judg, X.XCfg(start_invested=False, **kw))
    diff = float(np.max(np.abs(a["nav"].values - b["nav"].values)))
    same_states = bool((a["states"]["state"] == b["states"]["state"]).all())
    same_brake = bool((a["states"]["braked"] == b["states"]["braked"]).all())
    print(kw, "最大差(円)", diff, "状態一致", same_states, "ブレーキ一致", same_brake, "売買数", a["n_trades"], b["n_trades"], "税", round(a["tax_paid"]), round(b["tax_paid"]))
    ok &= diff == 0.0 and same_states and same_brake and a["n_trades"] == b["n_trades"]
print("回帰テスト", "合格（完全一致）" if ok else "不合格")
