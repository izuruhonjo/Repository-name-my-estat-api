#!/usr/bin/env bash
# LibreOffice で Excel の数式を再計算して out/recalc/ に保存する。
# 設定: 読み込み時に常に再計算 / 並列計算オフ（並列計算は誤って #VALUE! を出すことがある）
# 使い方: ./recalc.sh "out/ファイル名.xlsx"
set -e
P=/tmp/lo_profile_recalc
mkdir -p "$P/user" out/recalc
cat > "$P/user/registrymodifications.xcu" <<'XCU'
<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Calculation"><prop oor:name="UseThreadedCalculationForFormulaGroups" oor:op="fuse"><value>false</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Calculation"><prop oor:name="UseOpenCLSubsetOnly" oor:op="fuse"><value>false</value></prop></item>
</oor:items>
XCU
soffice -env:UserInstallation=file://$P --headless --convert-to xlsx --outdir out/recalc "$1"
