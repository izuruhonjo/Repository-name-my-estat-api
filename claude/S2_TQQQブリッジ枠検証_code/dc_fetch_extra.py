"""DC商品の基準価額履歴をワイズアドバイザー（Yahoo!ファイナンス投信）の公開CSVから取得し、DC一覧の基準価額と突き合わせる。
出典：https://apl.wealthadvisor.jp/webasp/yahoo-fund/fund/download.aspx?type=1&fnc=<協会コード>（日付,基準価額）。個人の研究用。"""
import subprocess, csv, io, time, re, sys, json
LIST = {r["番号"]: r for r in csv.DictReader(open("../DC商品ラインナップ_2026-11-09.csv", encoding="utf-8-sig")) if r["基準価額"]}
CAND = {  # 番号: 協会コードの候補（調査で出たもの。一覧の基準価額と一致したものだけ採用）
 "021": ["0131F122"], "030": ["01313156"], "001": ["0131601B"], "002": ["0131701B"], "003": ["0131801B"],
 "004": ["0131101B"], "005": ["3231101B"], "022": ["0431201B"], "023": ["32312984"], "006": ["0131202A"],
 "007": ["0131501B"], "008": ["01315027", "0131502B", "01318079"], "035": ["32314217"], "036": ["AW311205"],
 "009": ["4731501A"], "010": ["01312022"], "037": ["01316087"], "011": ["3531201B"], "024": ["03314022"],
 "012": ["0131102B"], "025": ["0331110A"], "020": ["01312054"], "026": ["01315087"],
}
extra = json.load(open("data_dc/extra_codes.json")) if len(sys.argv) > 1 else {}
CAND = {}
for k, v in extra.items(): CAND[k] = v
def num(s): return float(re.sub(r"[^\d.]", "", s))
def get(code):
    r = subprocess.run(["curl", "-sS", "-m", "60", f"https://apl.wealthadvisor.jp/webasp/yahoo-fund/fund/download.aspx?type=1&fnc={code}"], capture_output=True)
    try: t = r.stdout.decode("cp932")
    except Exception: return None
    rows = [l.split(",") for l in t.splitlines()[1:] if re.match(r"^\d{8},", l)]
    return rows or None
res = []
for no, cs in CAND.items():
    ok = None
    for c in cs:
        rows = get(c); time.sleep(1.0)
        if not rows: continue
        last = float(rows[-1][1]); lst = num(LIST[no]["基準価額"])
        hit = abs(last - lst) < 1.0
        res.append(dict(番号=no, 区分=LIST[no]["区分"], 略称=LIST[no]["略称"], コード=c, 開始=rows[0][0], 最終日=rows[-1][0], 最終値=last, 一覧値=lst, 一致=hit, 件数=len(rows)))
        if hit:
            with open(f"data_dc/{no}_{c}.csv", "w", newline="") as f:
                w = csv.writer(f); w.writerow(["date", "nav"]); w.writerows([[f"{r[0][:4]}-{r[0][4:6]}-{r[0][6:]}", r[1]] for r in rows])
            ok = c; break
    if not ok and not any(x["番号"] == no for x in res):
        res.append(dict(番号=no, 区分=LIST[no]["区分"], 略称=LIST[no]["略称"], コード="/".join(cs), 開始="", 最終日="", 最終値="", 一覧値=num(LIST[no]["基準価額"]), 一致=False, 件数=0))
import pandas as pd
d = pd.DataFrame(res); d.to_csv("data_dc/fetch_log_extra.csv", index=False, encoding="utf-8-sig")
pd.set_option("display.width", 220); print(d.to_string(index=False)); print("一致", int(d["一致"].sum()), "/", len(d))
