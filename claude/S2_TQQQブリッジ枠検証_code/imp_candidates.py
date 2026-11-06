"""
S2改良の候補（2026-11-06、結果を見る前に固定。数値は先行研究・一般的な目安で決め、最適化しない）
=====================================================================================
技法：39 促進の要因（imp_decomp.py の分解）、5 各種専門家の案（9つの視点）
制約：S2で買えるものだけ（ゴールドプラスGP・ニッセイNASDAQ100 N1・TQQQ・XLU・IEF・円現金）

促進の要因（分解の結果）
  ① 通常期（○・ブレーキなし）のGP 2倍が稼ぎのほぼ全部（年率寄与+18.0pt）
  ② ブレーキ期のGPは累計−55%（対数−0.81）。半分売りで−0.52に抑えている → 売る割合・判定が効く
  ③ 押し目期は持ち替えの摩擦（6営業日の入金待ち＋税）でN1持ちっぱなしより−0.19（対数）
  ④ 退避期はGPなら−0.79のところを+0.06。ここは役目を果たしている
  ⑤ 最大下落−36.1%（2015/6〜2016/6）は円高（125→100円）。GPは金とNASDAQの両脚に為替が掛かる
"""
import s2x as X

CANDIDATES = []   # (コード, 名前, 視点, XCfg の上書き, policy, judg の種類)


def add(code, name, view, cfg=None, policy=None, judg="base"):
    CANDIDATES.append(dict(code=code, name=name, view=view, cfg=cfg or {}, policy=policy, judg=judg))


def _base_core(c):
    return X.default_policy(c)


# ---------------- 金融工学（ボラ管理・レバレッジ） ----------------
add("K0", "ブレーキ継続（持ち替えの月もボラ30%以上なら半分のまま）", "運用の明確化", dict(keep_brake_on_switch=True))
add("K1", "ブレーキで全部売る（現状は半分）", "金融工学：ボラ管理", dict(brake_frac=1.0))
add("K4", "ブレーキの発動を25%に下げる", "金融工学：ボラ管理", dict(brake_th=0.25))
add("T3", "ブレーキの早期解除（日次でボラ25%未満なら翌営業日に戻す）", "テクニカル：ボラの平均回帰", dict(restore="daily", restore_th=0.25))


def calm_boost(w_t, vol_th=0.15, rate_max=None):
    def p(c):
        base = _base_core(c)
        if c["state"] == "NORMAL" and c.get("rv") == c.get("rv") and c["rv"] < vol_th \
                and (rate_max is None or c["rate"] < rate_max):
            return {"GP": 1 - w_t, "TQQQ": w_t}
        return base
    return p


add("K2", "静穏ブースト：通常かつ月末ボラ15%未満ならGP80%＋TQQQ20%", "金融工学：ボラ管理型レバ（Moreira-Muir 2017）",
    dict(keep_brake_on_switch=True), calm_boost(0.20))
add("K2a", "静穏ブースト（TQQQ10%）", "金融工学：感度", dict(keep_brake_on_switch=True), calm_boost(0.10))
add("K2b", "静穏ブースト（TQQQ30%）", "金融工学：感度", dict(keep_brake_on_switch=True), calm_boost(0.30))
add("K2r", "静穏ブースト（米短期金利3%未満のときだけ）", "マクロ：レバのコスト", dict(keep_brake_on_switch=True),
    calm_boost(0.20, rate_max=0.03))


def vol_target(target=0.20, cap=0.30):
    def p(c):
        base = _base_core(c)
        if c["state"] == "NORMAL" and c.get("rv") == c.get("rv") and c["rv"] > 0:
            w = min(max((target / c["rv"] - 1) / 2, 0.0), cap)
            w = round(w / 0.05) * 0.05          # 5%刻み（毎月の細かい売買を避ける）
            if w > 0:
                return {"GP": 1 - w, "TQQQ": w}
        return base
    return p


add("K3", "ボラ・ターゲット20%（通常のTQQQ比率＝(20%/ボラ−1)/2、上限30%）", "金融工学：ボラ・ターゲット（Harvey他 2018）",
    dict(keep_brake_on_switch=True), vol_target())

# ---------------- テクニカル ----------------
add("T1", "押し目の廃止（○はいつもGP）", "テクニカル／取引摩擦", None,
    lambda c: {"GP": 1.0} if c["state"] in ("NORMAL", "DIP") else _base_core(c))
add("T2", "買い戻しラインを9ヶ月→6ヶ月平均に", "テクニカル：復帰の遅れ（2009・2019・2023）", None, None, judg="buy6")

# ---------------- 為替・国際政治経済 ----------------
add("X1", "円高ガード：USDJPYが12ヶ月平均を下回る通常月はN1（為替の掛かりを2倍→1倍）", "為替",
    None, lambda c: {"N1": 1.0} if (c["state"] == "NORMAL" and c["fx"] < c["fx_sma12"]) else _base_core(c))
add("X2", "円急騰ブレーキ：USDJPYが20営業日で−5%以下でもブレーキ", "為替・国際政治経済（円キャリーの巻き戻し）",
    dict(fx_brake=-0.05))

# ---------------- ゴールド・地政学 ----------------
add("G1", "金ガード：円建て金が12ヶ月平均を下回る通常月はN1（前回48通りで不採用の再確認）", "ゴールド",
    None, lambda c: {"N1": 1.0} if (c["state"] == "NORMAL" and c["gold_jpy"] < c["gold_jpy_sma12"]) else _base_core(c))
add("P1", "有事ブレーキ：金が20営業日で+7%以上かつQQQが−5%以下でもブレーキ", "地政学（有事の金買い・株売り）",
    dict(geo_brake=(0.07, -0.05)))

# ---------------- NASDAQ・AI/テック ----------------
add("S1", "半導体先行ガード：SMHが10ヶ月平均を下回る通常月はN1", "AI・テック（半導体はNASDAQの先行指標）",
    None, lambda c: {"N1": 1.0} if (c["state"] == "NORMAL" and c["smh"] < c["smh_sma10"]) else _base_core(c))

# ---------------- 退避（データサイエンス・金利） ----------------
add("R0", "退避は円現金だけ（守り待避をやめる）", "データサイエンス：守り待避の価値の確認",
    None, lambda c: {"CASH": 1.0} if c["state"] == "RETREAT" else _base_core(c))
add("R1", "退避はIEF（円建て）が12ヶ月平均より上のときだけIEF、ほかは円現金", "金利・国際政治経済（有事の米国債）",
    None, lambda c: ({"IEFJ": 1.0} if c["ief_jpy"] > c["ief_jpy_sma12"] else {"CASH": 1.0}) if c["state"] == "RETREAT" else _base_core(c))

# =====================================================================
# 事後の組み合わせ（単独の結果を見たあとに追加。PBO・DSRの試行数に含める）
# =====================================================================
COMBOS = []


def addc(code, name, cfg=None, policy=None, judg="base"):
    COMBOS.append(dict(code=code, name=name, view="事後の組み合わせ", cfg=cfg or {}, policy=policy, judg=judg))


addc("C1", "K0＋P1（ブレーキ継続＋有事ブレーキ）", dict(keep_brake_on_switch=True, geo_brake=(0.07, -0.05)))
addc("C2", "K1＋P1（全部売り＋有事ブレーキ）", dict(brake_frac=1.0, geo_brake=(0.07, -0.05)))
addc("C3", "K0＋K1（全部売り＋ブレーキ継続）", dict(brake_frac=1.0, keep_brake_on_switch=True))
addc("C4", "K0＋K1＋P1", dict(brake_frac=1.0, keep_brake_on_switch=True, geo_brake=(0.07, -0.05)))
addc("C5", "K1＋K2r（全部売り＋低金利の静穏ブースト）", dict(brake_frac=1.0, keep_brake_on_switch=True), calm_boost(0.20, rate_max=0.03))
addc("C6", "K0＋K1＋P1＋K2r", dict(brake_frac=1.0, keep_brake_on_switch=True, geo_brake=(0.07, -0.05)), calm_boost(0.20, rate_max=0.03))
addc("C7", "K0＋P1＋K2r（半分売りのまま）", dict(keep_brake_on_switch=True, geo_brake=(0.07, -0.05)), calm_boost(0.20, rate_max=0.03))
addc("C8", "ブレーキで75%売る＋K0＋P1", dict(brake_frac=0.75, keep_brake_on_switch=True, geo_brake=(0.07, -0.05)))
addc("C9", "T1＋K1（押し目廃止＋全部売り）", dict(brake_frac=1.0),
     lambda c: {"GP": 1.0} if c["state"] in ("NORMAL", "DIP") else _base_core(c))


def const_boost(w_t):
    def p(c):
        if c["state"] == "NORMAL":
            return {"GP": 1 - w_t, "TQQQ": w_t}
        return _base_core(c)
    return p


# C10（K0＋T1）は T1 と日次NAVが完全に同じだったため試行から外した（押し目がなければ K0 が働く場面がない）
addc("L10", "参考：通常はいつもGP90%＋TQQQ10%（K0込み）", dict(keep_brake_on_switch=True), const_boost(0.10))
addc("L20", "参考：通常はいつもGP80%＋TQQQ20%（K0込み）", dict(keep_brake_on_switch=True), const_boost(0.20))
