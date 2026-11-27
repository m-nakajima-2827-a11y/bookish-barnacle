#!/usr/bin/env python3
"""入力済みの収支管理ブックを読み取り、月次損益・年間推移・要注意ポイントを Markdown で出力する。

使い方:
    python analyze_workbook.py 入力済み.xlsx                 # 設定シートの対象月で集計
    python analyze_workbook.py 入力済み.xlsx --month 2027-05  # 対象月を指定（ブックは書き換えない）

openpyxl で書いたブックや Googleスプレッドシートからダウンロードした .xlsx には
計算結果が保存されていないことがあるため、LibreOffice（soffice）があれば
一時フォルダで再計算してから読み取ります。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile

from openpyxl import load_workbook


def recalc(path: str, month: str | None) -> str:
    """一時コピーを作り、必要なら対象月を書き換えて LibreOffice で再計算する。"""
    tmpdir = tempfile.mkdtemp(prefix="crepe_")
    src = os.path.join(tmpdir, "src.xlsx")
    shutil.copy(path, src)
    if month:
        wb = load_workbook(src)
        y, m = map(int, month.split("-"))
        wb["設定"]["B5"] = dt.date(y, m, 1)
        wb.save(src)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        print("警告: LibreOffice が見つからないため、保存済みの計算結果をそのまま読み取ります。", file=sys.stderr)
        return src
    outdir = os.path.join(tmpdir, "out")
    os.makedirs(outdir)
    subprocess.run([soffice, "--headless", "--calc", "--convert-to", "xlsx", "--outdir", outdir, src],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    return os.path.join(outdir, "src.xlsx")


def yen(v) -> str:
    return f"{v:,.0f}円" if isinstance(v, (int, float)) else "-"


def pct(v) -> str:
    return f"{v * 100:.1f}%" if isinstance(v, (int, float)) else "-"


def num(v) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--month", help="YYYY-MM")
    a = ap.parse_args()

    wb = load_workbook(recalc(a.path, a.month), data_only=True)
    pl = wb["月次損益"]
    rows = {}
    for r in range(6, pl.max_row + 1):
        label = pl.cell(row=r, column=1).value
        if isinstance(label, str) and label and not label.startswith("■"):
            rows[label] = [pl.cell(row=r, column=c).value for c in range(2, 7)]
    channels = [pl.cell(row=5, column=c).value for c in range(2, 7)]
    month = pl["B3"].value
    shop = wb["設定"]["B3"].value

    def g(label, i):
        return rows.get(label, [None] * 5)[i]

    out = [f"# 収支レポート：{shop}　{month:%Y年%m月}" if isinstance(month, dt.datetime) else "# 収支レポート", ""]
    out.append("> 金額は税抜。ブックの入力値から自動集計した結果です（推定・試算は含みません）。\n")

    out.append("## 1. チャネル別損益\n")
    out.append("| 項目 | " + " | ".join(str(c) for c in channels) + " |")
    out.append("|---|" + "---:|" * len(channels))
    show = [("売上高（税抜）", yen), ("販売数（個）", num), ("1個あたり売上（税抜）", yen), ("売上原価", yen),
            ("粗利（売上総利益）", yen), ("粗利率", pct), ("変動費 計", yen), ("限界利益", yen), ("固定費 計", yen),
            ("チャネル貢献利益", yen), ("共通費配賦額", yen), ("営業利益", yen), ("営業利益率", pct)]
    for label, f in show:
        out.append(f"| {label} | " + " | ".join(f(v) for v in rows.get(label, [None] * 5)) + " |")

    out.append("\n## 2. 経営指標\n")
    out.append("| 指標 | " + " | ".join(str(c) for c in channels) + " |")
    out.append("|---|" + "---:|" * len(channels))
    for label, f in [("原価率（実際）", pct), ("原価率（理論）", pct), ("原価差異（実際−理論）", yen), ("廃棄原価", yen),
                     ("人件費率", pct), ("FL比率（原価＋人件費）", pct), ("損益分岐点売上（共通費配賦後）", yen),
                     ("損益分岐点販売数（個/月）", num), ("安全余裕率", pct), ("目標営業利益に必要な販売数（個/月）", num)]:
        out.append(f"| {label} | " + " | ".join(f(v) for v in rows.get(label, [None] * 5)) + " |")

    # --- 要注意ポイント（ルールベース） ---
    alerts = []
    for i, ch in enumerate(channels[:3]):
        op, sales = g("営業利益", i), g("売上高（税抜）", i)
        if isinstance(op, (int, float)) and isinstance(sales, (int, float)) and sales > 0:
            if op < 0:
                alerts.append(f"**{ch}** が営業赤字（{yen(op)}）。損益分岐点売上 {yen(g('損益分岐点売上（共通費配賦後）', i))} に対し実績 {yen(sales)}。")
            real, theo = g("原価率（実際）", i), g("原価率（理論）", i)
            if isinstance(real, float) and isinstance(theo, float) and real - theo > 0.03:
                alerts.append(f"**{ch}** の実際原価率 {pct(real)} が理論原価率 {pct(theo)} を3pt以上（目安）上回っています（廃棄・盛りすぎ・記録漏れ・仕入値上がりを確認）。")
            fl = g("FL比率（原価＋人件費）", i)
            if isinstance(fl, float) and fl > 0.65:
                alerts.append(f"**{ch}** のFL比率が {pct(fl)}。原価と人件費で売上の65%（目安）超を占めています。")
    chk = g("経費入力の当月合計 − 損益計上額", 4)
    if isinstance(chk, (int, float)) and abs(chk) > 0.5:
        alerts.append(f"経費入力に損益へ計上されていない金額が {yen(chk)} あります（費目・チャネルの未登録／空欄）。")
    prd = wb["商品マスタ"]
    for r in range(4, prd.max_row + 1):
        name, judge, rate = prd.cell(row=r, column=1).value, prd.cell(row=r, column=8).value, prd.cell(row=r, column=6).value
        if name and judge and judge != "OK":
            alerts.append(f"商品『{name}』：{judge}（原価率 {pct(rate)}）")
    out.append("\n## 3. 要注意ポイント（自動判定・しきい値は目安）\n")
    out += [f"- {x}" for x in alerts] or ["- 自動判定で検出された項目はありません。"]

    yr = wb["年間推移"]
    out.append("\n## 4. 年間推移\n")
    out.append("| 月 | 売上合計 | 粗利率 | 営業利益 | 累計営業利益 |")
    out.append("|---|---:|---:|---:|---:|")
    for r in range(5, 17):
        m = yr.cell(row=r, column=1).value
        sales = yr.cell(row=r, column=5).value
        if isinstance(sales, (int, float)) and sales == 0:
            continue
        out.append(f"| {m:%Y/%m} | {yen(sales)} | {pct(yr.cell(row=r, column=9).value)} | "
                   f"{yen(yr.cell(row=r, column=12).value)} | {yen(yr.cell(row=r, column=15).value)} |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
