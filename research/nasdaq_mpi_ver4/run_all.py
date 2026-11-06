"""全工程: daily構築 → ケースA/B/C×戦略×積立×期間 → 頑健性 → Excel/グラフ
実行: ./fetch_data.sh && python3 run_all.py   (Excel数式の再計算は LibreOffice で --convert-to xlsx)"""
import sys, subprocess; sys.path.insert(0, '.')
from mpi import *
daily = build_daily(); daily.to_pickle('data/daily.pkl')
m = monthly_bars(daily).loc[:'2026-10']; s = signals(m)
pd.to_pickle(intrabar_exec(daily, m), 'data/intrabar.pkl')
cost3, _ = calibrate_cost(daily, 'TQQQ', 3)
A = Cfg(name='A 記事条件')
B = replace(A, name='B +ファンドコスト/配当/翌日約定', lev_cost=cost3, financing=True, one_er=0.0015, dividends=True, exec_lag=1, contrib_at_month_end=False)
C = replace(B, name='C +SBI手数料/為替/日本税制', commission=0.00495, comm_cap_usd=22, slippage=0.0002, fx=True, jp_tax=True, div_tax=True)
C25 = replace(C, name='C 円貨決済(25銭)', fx_fee_yen=0.25)
rows = []
for end in ['2022-08', '2026-10']:
    for infl in [True, False]:
        for cfg in [A, B, C, C25]:
            for strat in ['mpi', 'dca3', 'dca1']:
                r, h, t = run(daily, s, replace(cfg, end=end, infl_adj=infl, strategy=strat))
                r.pop('taxlog', None)
                r.update(strategy=strat, infl='物価調整' if infl else '名目3万', period=end); rows.append(r)
pd.DataFrame(rows).to_pickle('data/results.pkl')
for f in ['robust.py', 'build_report.py', 'charts.py', 'oos.py', 'oos_report.py']:
    subprocess.run([sys.executable, f], check=True)
