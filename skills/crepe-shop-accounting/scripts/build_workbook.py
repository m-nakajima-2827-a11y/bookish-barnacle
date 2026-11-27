#!/usr/bin/env python3
"""クレープ店 収支管理ワークブック（Excel / Googleスプレッドシート対応）を生成する。

使い方:
    python build_workbook.py --out crepe_accounting.xlsx            # 空のテンプレート
    python build_workbook.py --out crepe_sample.xlsx --sample       # 動作確認用サンプル（架空データ）入り
    python build_workbook.py --out x.xlsx --shop "〇〇クレープ" --fy-start 2027-04-01

生成されるシート:
    使い方 / 設定 / 材料マスタ / レシピ / 商品マスタ / 費目マスタ / 設備 /
    売上入力 / 経費入力 / 棚卸 / 月次損益 / 年間推移 / シミュレーション

関数は Excel と Googleスプレッドシートの両方で動くもの（SUMIFS, VLOOKUP, IFERROR,
EDATE, EOMONTH, ROUND など）だけを使っています。Googleドライブにアップロードして
「Googleスプレッドシートとして開く」でそのまま使えます。
"""
from __future__ import annotations

import argparse
import datetime as dt
import random

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# ---------------------------------------------------------------------------
# 定数・スタイル
# ---------------------------------------------------------------------------
CHANNELS = ["店舗", "キッチンカー", "自販機"]
COMMON = "共通"

# 行数（入力枠）
N_MATERIAL = 200
N_RECIPE = 600
N_PRODUCT = 100
N_EQUIP = 50
N_SALES = 3000
N_EXPENSE = 2000
N_STOCK = 200
N_EXPENSE_MASTER = 40

# 費目マスタ（費目, P&L区分, 既定税率, 説明）
# 区分: 売上原価 / 変動費 / 固定費
EXPENSE_ITEMS = [
    ("材料仕入", "売上原価", 0.08, "生地・クリーム・果物・チョコ等の食材。軽減税率8%"),
    ("包材仕入", "売上原価", 0.10, "クレープ紙・袋・自販機用容器・ラベル"),
    ("決済手数料", "変動費", 0.0, "キャッシュレス決済手数料（非課税扱いが一般的）"),
    ("自販機設置手数料", "変動費", 0.10, "設置場所への売上歩合・場所代"),
    ("出店料", "変動費", 0.10, "キッチンカーの出店料・イベント出店料・売上歩合"),
    ("燃料費", "変動費", 0.10, "キッチンカーのガソリン・発電機燃料・ガスボンベ"),
    ("消耗品費", "変動費", 0.10, "手袋・洗剤・紙ナプキン等"),
    ("人件費", "固定費", 0.0, "給与・アルバイト代・法定福利費（不課税）"),
    ("家賃", "固定費", 0.10, "店舗家賃・共益費"),
    ("駐車場代", "固定費", 0.10, "キッチンカーの保管駐車場"),
    ("水道光熱費", "固定費", 0.10, "電気・ガス・水道（自販機の電気代を含む）"),
    ("リース料", "固定費", 0.10, "機器のリース・レンタル料"),
    ("通信費", "固定費", 0.10, "電話・ネット・POS/決済端末の月額"),
    ("販促費", "固定費", 0.10, "チラシ・SNS広告・ノベルティ・ポイント原資"),
    ("車両維持費", "固定費", 0.10, "キッチンカーの車検・整備・保険以外の維持費"),
    ("修繕費", "固定費", 0.10, "設備・店舗の修理"),
    ("保険料", "固定費", 0.0, "火災保険・車両保険・PL保険（非課税）"),
    ("衛生・許可費", "固定費", 0.0, "営業許可・検便・害虫駆除等（印紙・証紙は不課税）"),
    ("支払報酬", "固定費", 0.10, "税理士・デザイナー等への報酬"),
    ("雑費", "固定費", 0.10, "上記に当てはまらない少額経費"),
]

FONT_NAME = "Meiryo"
C_HEAD = "1F4E79"
C_SUB = "DDEBF7"
C_INPUT = "FFF2CC"
C_CALC = "F2F2F2"
C_TOTAL = "E2EFDA"
C_WARN = "F8CBAD"

thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)

F_TITLE = Font(name=FONT_NAME, size=14, bold=True, color=C_HEAD)
F_HEAD = Font(name=FONT_NAME, size=10, bold=True, color="FFFFFF")
F_BOLD = Font(name=FONT_NAME, size=10, bold=True)
F_BASE = Font(name=FONT_NAME, size=10)
F_NOTE = Font(name=FONT_NAME, size=9, color="595959")

FILL_HEAD = PatternFill("solid", fgColor=C_HEAD)
FILL_SUB = PatternFill("solid", fgColor=C_SUB)
FILL_INPUT = PatternFill("solid", fgColor=C_INPUT)
FILL_CALC = PatternFill("solid", fgColor=C_CALC)
FILL_TOTAL = PatternFill("solid", fgColor=C_TOTAL)

FMT_YEN = '#,##0;[Red]-#,##0'
FMT_YEN_DEC = '#,##0.0;[Red]-#,##0.0'
FMT_PCT = '0.0%'
FMT_DATE = 'yyyy/mm/dd'
FMT_MONTH = 'yyyy"年"m"月"'
FMT_NUM = '#,##0'


def q(sheet: str) -> str:
    """シート名をクォートして参照用の接頭辞にする。"""
    return f"'{sheet}'!"


S_GUIDE = "使い方"
S_SET = "設定"
S_MAT = "材料マスタ"
S_REC = "レシピ"
S_PRD = "商品マスタ"
S_EXM = "費目マスタ"
S_EQP = "設備"
S_SAL = "売上入力"
S_EXP = "経費入力"
S_STK = "棚卸"
S_PL = "月次損益"
S_YR = "年間推移"
S_SIM = "シミュレーション"

# 設定シートのセル位置
SET_SHOP = "$B$3"
SET_FY = "$B$4"
SET_MONTH = "$B$5"
SET_TAX_STD = "$B$6"
SET_TAX_RED = "$B$7"
SET_ALLOC = "$B$8"
SET_TARGET = "$B$9"
SET_COST_TARGET = "$B$10"
SET_CH_ROW0 = 13  # 店舗=13, キッチンカー=14, 自販機=15, 共通=16


def ch_cell(i: int) -> str:
    return f"{q(S_SET)}$A${SET_CH_ROW0 + i}"


def ch_rate(i: int) -> str:
    return f"{q(S_SET)}$B${SET_CH_ROW0 + i}"


# ---------------------------------------------------------------------------
# 汎用ヘルパー
# ---------------------------------------------------------------------------
def title(ws, text: str, note: str | None = None):
    ws["A1"] = text
    ws["A1"].font = F_TITLE
    if note:
        ws["A2"] = note
        ws["A2"].font = F_NOTE
    ws.sheet_view.showGridLines = False


def header(ws, row: int, labels: list[str], widths: list[float] | None = None):
    for c, label in enumerate(labels, start=1):
        cell = ws.cell(row=row, column=c, value=label)
        cell.font = F_HEAD
        cell.fill = FILL_HEAD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[row].height = 30
    if widths:
        for c, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(c)].width = w


def style_cell(cell, *, kind: str = "calc", fmt: str | None = None, bold: bool = False):
    cell.font = F_BOLD if bold else F_BASE
    cell.border = BORDER
    if kind == "input":
        cell.fill = FILL_INPUT
    elif kind == "calc":
        cell.fill = FILL_CALC
    elif kind == "total":
        cell.fill = FILL_TOTAL
    elif kind == "sub":
        cell.fill = FILL_SUB
    if fmt:
        cell.number_format = fmt


def style_range(ws, first_row: int, last_row: int, cols: dict[int, tuple[str, str | None]]):
    """cols = {列番号: (kind, number_format)}"""
    for r in range(first_row, last_row + 1):
        for c, (kind, fmt) in cols.items():
            style_cell(ws.cell(row=r, column=c), kind=kind, fmt=fmt)


def add_list_validation(ws, formula: str, rng: str, prompt: str | None = None):
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False)
    dv.error = "リストから選択してください"
    dv.errorTitle = "入力エラー"
    if prompt:
        dv.prompt = prompt
        dv.showInputMessage = True
    ws.add_data_validation(dv)
    dv.add(rng)


def col_ref(sheet: str, col: str) -> str:
    return f"{q(sheet)}${col}:${col}"


# ---------------------------------------------------------------------------
# 各シート
# ---------------------------------------------------------------------------
def build_guide(wb, sample: bool):
    ws = wb.create_sheet(S_GUIDE)
    title(ws, "クレープ店 収支管理ブック ― 使い方")
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 90
    rows = [
        ("", "■ 基本ルール", ""),
        ("", "黄色のセル", "入力するセルです。灰色・緑色のセルは計算式なので上書きしないでください。"),
        ("", "金額の扱い", "損益はすべて『税抜』で集計します。売上は税込で入力し、税率から税抜に自動換算します。"),
        ("", "チャネル", "店舗 / キッチンカー / 自販機 の3つ。どのチャネルにも紐づかない経費は『共通』で入力します。"),
        ("", "", ""),
        ("", "■ 初期設定（最初に1回）", ""),
        ("", "1. 設定", "店舗名、事業年度の開始日、表示したい月、配賦方法、目標営業利益を入力します。"),
        ("", "2. 材料マスタ", "食材・包材を『購入価格・購入量・単位・歩留まり』で登録します。使用単価が自動計算されます。"),
        ("", "3. レシピ", "商品ごとに使う材料と使用量を1行ずつ登録します（例：バナナチョコ／バナナ／60g）。"),
        ("", "4. 商品マスタ", "商品名と販売価格（税込）を登録します。1個あたりの材料原価・原価率・粗利が自動表示されます。"),
        ("", "5. 設備", "厨房機器・キッチンカー車両・自販機など、資産計上した設備を登録します。月額の減価償却費が損益に自動計上されます。"),
        ("", "", ""),
        ("", "■ 日々・月次の入力", ""),
        ("", "6. 売上入力（毎日）", "日付・チャネル・商品・販売数・廃棄数を入力します。POSの商品別日報をそのまま貼り付けても構いません。"),
        ("", "7. 経費入力（都度）", "日付・費目・チャネル・税込金額を入力します。税率を空欄にすると費目マスタの既定税率で税抜換算します。"),
        ("", "8. 棚卸（月末）", "月末に残っている材料・包材の金額（税抜）をチャネルごとに入力します。正確な売上原価の計算に使います。"),
        ("", "", ""),
        ("", "■ 確認する", ""),
        ("", "9. 月次損益", "設定シートで指定した月のチャネル別損益・原価率・損益分岐点を表示します。"),
        ("", "10. 年間推移", "事業年度12か月の売上・利益の推移とグラフを表示します。"),
        ("", "11. シミュレーション", "価格改定・原価変動・販売数の増減が利益にどう影響するかを試算します。"),
        ("", "", ""),
        ("", "■ 注意", ""),
        ("", "税務", "このブックは経営管理（管理会計）用です。消費税・減価償却・確定申告の最終判断は税理士にご確認ください。"),
        ("", "減価償却", "設備シートで自動計上するため、同じ設備を経費入力の『リース料』等に重複入力しないでください。"),
        ("", "費目の追加", "費目マスタの空欄行に追加できます。区分（売上原価／変動費／固定費）を必ず選んでください。"),
    ]
    if sample:
        rows.insert(0, ("", "★ サンプルデータ", "このファイルの数値は動作確認用の架空データです。実際の数値ではありません。実データに置き換えてご利用ください。"))
    for i, (a, b, c) in enumerate(rows, start=3):
        ws.cell(row=i, column=2, value=b).font = F_BOLD if b.startswith(("■", "★")) else F_BASE
        cell = ws.cell(row=i, column=3, value=c)
        cell.font = F_BASE
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if b.startswith("★"):
            ws.cell(row=i, column=2).fill = PatternFill("solid", fgColor=C_WARN)
            cell.fill = PatternFill("solid", fgColor=C_WARN)
    legend_row = len(rows) + 5
    ws.cell(row=legend_row, column=2, value="凡例").font = F_BOLD
    for i, (kind, label) in enumerate([("input", "入力セル"), ("calc", "計算セル（触らない）"), ("total", "合計・重要指標")]):
        c = ws.cell(row=legend_row + 1 + i, column=2, value=label)
        style_cell(c, kind=kind)


def build_settings(wb, shop: str, fy_start: dt.date, month: dt.date, sample: bool):
    ws = wb.create_sheet(S_SET)
    title(ws, "設定", "黄色のセルを入力してください。ここの値が全シートの集計に使われます。")
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 60
    items = [
        (3, "店舗名", shop, None, "表示用"),
        (4, "事業年度の開始日", fy_start, FMT_DATE, "年間推移の1か月目（例：2027/04/01）"),
        (5, "月次損益で表示する月（1日を入力）", month, FMT_DATE, "例：2027/05/01 と入力すると5月の損益を表示"),
        (6, "標準税率", 0.10, FMT_PCT, "イートイン・一般の経費"),
        (7, "軽減税率", 0.08, FMT_PCT, "持ち帰り・食材"),
        (8, "共通費の配賦方法", "売上比", None, "『売上比』＝各チャネルの売上割合で配賦 ／ 『手入力』＝下表の配賦率で配賦"),
        (9, "目標営業利益（月・税抜）", 0 if not sample else 300000, FMT_YEN, "月次損益で『目標達成に必要な販売数』を計算します"),
        (10, "目標原価率（目安）", 0.30, FMT_PCT, "商品マスタで超過商品に『要見直し』を表示。自店の方針に合わせて変更"),
    ]
    for r, label, val, fmt, note in items:
        ws.cell(row=r, column=1, value=label).font = F_BOLD
        style_cell(ws.cell(row=r, column=1), kind="sub", bold=True)
        c = ws.cell(row=r, column=2, value=val)
        style_cell(c, kind="input", fmt=fmt)
        ws.cell(row=r, column=4, value=note).font = F_NOTE
    add_list_validation(ws, '"売上比,手入力"', "B8")

    header_row = SET_CH_ROW0 - 1
    for c, label in enumerate(["チャネル", "手入力時の配賦率", "既定の販売区分", "メモ"], start=1):
        cell = ws.cell(row=header_row, column=c, value=label)
        cell.font = F_HEAD
        cell.fill = FILL_HEAD
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center")
    rates = [0.5, 0.3, 0.2]
    memos = ["実店舗", "移動販売・イベント出店", "店舗設置型冷蔵自販機"]
    for i, ch in enumerate(CHANNELS):
        r = SET_CH_ROW0 + i
        style_cell(ws.cell(row=r, column=1, value=ch), kind="input", bold=True)
        style_cell(ws.cell(row=r, column=2, value=rates[i]), kind="input", fmt=FMT_PCT)
        style_cell(ws.cell(row=r, column=3, value="持ち帰り"), kind="input")
        style_cell(ws.cell(row=r, column=4, value=memos[i]), kind="input")
    r = SET_CH_ROW0 + 3
    style_cell(ws.cell(row=r, column=1, value=COMMON), kind="calc", bold=True)
    style_cell(ws.cell(row=r, column=2, value="―"), kind="calc")
    style_cell(ws.cell(row=r, column=3, value="―"), kind="calc")
    style_cell(ws.cell(row=r, column=4, value="経費専用：本部費・会計ソフト・税理士報酬など、チャネルに直接紐づかない経費"), kind="calc")
    r += 1
    ws.cell(row=r, column=1, value="配賦率の合計（手入力時は100%に）").font = F_NOTE
    c = ws.cell(row=r, column=2, value=f"=SUM(B{SET_CH_ROW0}:B{SET_CH_ROW0 + 2})")
    style_cell(c, kind="calc", fmt=FMT_PCT)
    add_list_validation(ws, '"持ち帰り,イートイン"', f"C{SET_CH_ROW0}:C{SET_CH_ROW0 + 2}")
    ws.cell(row=r + 2, column=1, value="※ チャネル名を変更すると全シートに反映されます（売上・経費入力の既存データのチャネル名も合わせて変更してください）。").font = F_NOTE


def build_materials(wb, sample: bool):
    ws = wb.create_sheet(S_MAT)
    title(ws, "材料マスタ", "購入価格は税抜。歩留まり率＝実際に使える割合（例：バナナの皮を除くと65%）。空欄は100%として計算します。")
    header(ws, 3, ["材料名", "区分", "仕入先", "購入価格\n(税抜)", "購入量", "単位", "歩留まり率", "使用単価\n(円/単位)", "メモ"],
           [22, 10, 16, 12, 10, 8, 11, 13, 30])
    first, last = 4, 3 + N_MATERIAL
    for r in range(first, last + 1):
        ws.cell(row=r, column=8, value=f'=IF(OR(A{r}="",E{r}=0,E{r}=""),"",D{r}/(E{r}*IF(G{r}="",1,G{r})))')
    style_range(ws, first, last, {1: ("input", None), 2: ("input", None), 3: ("input", None), 4: ("input", FMT_YEN),
                                  5: ("input", FMT_NUM), 6: ("input", None), 7: ("input", FMT_PCT),
                                  8: ("calc", '#,##0.000'), 9: ("input", None)})
    add_list_validation(ws, '"食材,包材,その他"', f"B{first}:B{last}")
    add_list_validation(ws, '"g,ml,個,枚,本,袋"', f"F{first}:F{last}")
    ws.freeze_panes = "B4"
    if sample:
        data = [
            ("薄力粉", "食材", 1800, 10000, "g", None),
            ("牛乳", "食材", 220, 1000, "ml", None),
            ("卵", "食材", 300, 10, "個", None),
            ("砂糖", "食材", 250, 1000, "g", None),
            ("バター", "食材", 550, 200, "g", None),
            ("生クリーム", "食材", 700, 1000, "ml", None),
            ("ホイップ用砂糖", "食材", 250, 1000, "g", None),
            ("バナナ", "食材", 200, 600, "g", 0.65),
            ("いちご", "食材", 800, 300, "g", 0.95),
            ("チョコソース", "食材", 900, 1000, "g", None),
            ("カスタード", "食材", 1100, 1000, "g", None),
            ("ツナ", "食材", 1500, 1000, "g", None),
            ("レタス", "食材", 180, 300, "g", 0.8),
            ("チーズ", "食材", 1200, 1000, "g", None),
            ("クレープ包み紙", "包材", 1500, 500, "枚", None),
            ("自販機用容器", "包材", 3500, 100, "個", None),
            ("ラベルシール", "包材", 800, 500, "枚", None),
        ]
        for i, (name, kind, price, qty, unit, yld) in enumerate(data):
            r = first + i
            ws.cell(row=r, column=1, value=name)
            ws.cell(row=r, column=2, value=kind)
            ws.cell(row=r, column=3, value="（サンプル）")
            ws.cell(row=r, column=4, value=price)
            ws.cell(row=r, column=5, value=qty)
            ws.cell(row=r, column=6, value=unit)
            if yld:
                ws.cell(row=r, column=7, value=yld)


SAMPLE_BATTER = [("薄力粉", 30), ("牛乳", 60), ("卵", 0.3), ("砂糖", 5), ("バター", 3)]
SAMPLE_RECIPES = {
    "バナナチョコ生クリーム": [("生クリーム", 40), ("ホイップ用砂糖", 4), ("バナナ", 60), ("チョコソース", 15), ("クレープ包み紙", 1)],
    "いちご生クリーム": [("生クリーム", 40), ("ホイップ用砂糖", 4), ("いちご", 50), ("クレープ包み紙", 1)],
    "カスタードバナナ": [("カスタード", 50), ("バナナ", 60), ("クレープ包み紙", 1)],
    "ツナチーズ": [("ツナ", 40), ("チーズ", 20), ("レタス", 15), ("クレープ包み紙", 1)],
    "冷やしクレープ（自販機）": [("生クリーム", 45), ("ホイップ用砂糖", 4), ("カスタード", 20), ("いちご", 30),
                         ("自販機用容器", 1), ("ラベルシール", 1)],
}
SAMPLE_PRODUCTS = [
    ("バナナチョコ生クリーム", "スイーツ", 700),
    ("いちご生クリーム", "スイーツ", 800),
    ("カスタードバナナ", "スイーツ", 650),
    ("ツナチーズ", "おかず", 750),
    ("冷やしクレープ（自販機）", "自販機", 700),
]


def build_recipes(wb, sample: bool):
    ws = wb.create_sheet(S_REC)
    title(ws, "レシピ（原価計算）", "商品1つに使う材料を1行ずつ登録します。商品名は商品マスタと完全一致させてください。")
    header(ws, 3, ["商品名", "材料名", "使用量", "単位", "使用単価", "材料原価\n(円/個)", "メモ"], [26, 20, 10, 8, 12, 12, 30])
    first, last = 4, 3 + N_RECIPE
    mat = f"{q(S_MAT)}$A:$H"
    for r in range(first, last + 1):
        ws.cell(row=r, column=4, value=f'=IF(B{r}="","",IFERROR(VLOOKUP(B{r},{mat},6,FALSE),"未登録"))')
        ws.cell(row=r, column=5, value=f'=IF(B{r}="","",IFERROR(VLOOKUP(B{r},{mat},8,FALSE),0))')
        ws.cell(row=r, column=6, value=f'=IF(OR(B{r}="",C{r}=""),"",C{r}*N(E{r}))')
    style_range(ws, first, last, {1: ("input", None), 2: ("input", None), 3: ("input", '#,##0.0'), 4: ("calc", None),
                                  5: ("calc", '#,##0.000'), 6: ("calc", FMT_YEN_DEC), 7: ("input", None)})
    add_list_validation(ws, f"{q(S_PRD)}$A$4:$A${3 + N_PRODUCT}", f"A{first}:A{last}")
    add_list_validation(ws, f"{q(S_MAT)}$A$4:$A${3 + N_MATERIAL}", f"B{first}:B{last}")
    ws.conditional_formatting.add(f"D{first}:D{last}", CellIsRule(operator="equal", formula=['"未登録"'],
                                                               fill=PatternFill("solid", fgColor=C_WARN)))
    ws.freeze_panes = "A4"
    if sample:
        r = first
        for prod, items in SAMPLE_RECIPES.items():
            batter = SAMPLE_BATTER if "自販機" not in prod else SAMPLE_BATTER
            for name, qty in batter + items:
                ws.cell(row=r, column=1, value=prod)
                ws.cell(row=r, column=2, value=name)
                ws.cell(row=r, column=3, value=qty)
                r += 1


def build_products(wb, sample: bool):
    ws = wb.create_sheet(S_PRD)
    title(ws, "商品マスタ", "販売価格は税込で入力。原価率は持ち帰り（軽減税率）の税抜価格に対する材料原価の割合です。")
    header(ws, 3, ["商品名", "カテゴリ", "販売価格\n(税込)", "材料原価\n(円/個)", "税抜価格\n(持ち帰り)", "原価率",
                   "粗利\n(円/個)", "判定", "メモ"], [26, 12, 12, 12, 12, 10, 12, 12, 30])
    first, last = 4, 3 + N_PRODUCT
    red = f"{q(S_SET)}{SET_TAX_RED}"
    tgt = f"{q(S_SET)}{SET_COST_TARGET}"
    for r in range(first, last + 1):
        ws.cell(row=r, column=4, value=f'=IF(A{r}="","",SUMIF({col_ref(S_REC, "A")},A{r},{col_ref(S_REC, "F")}))')
        ws.cell(row=r, column=5, value=f'=IF(OR(A{r}="",C{r}=""),"",C{r}/(1+{red}))')
        ws.cell(row=r, column=6, value=f'=IF(OR(A{r}="",C{r}="",C{r}=0),"",D{r}/E{r})')
        ws.cell(row=r, column=7, value=f'=IF(OR(A{r}="",C{r}=""),"",E{r}-D{r})')
        ws.cell(row=r, column=8, value=f'=IF(F{r}="","",IF(D{r}=0,"レシピ未登録",IF(F{r}>{tgt},"要見直し","OK")))')
    style_range(ws, first, last, {1: ("input", None), 2: ("input", None), 3: ("input", FMT_YEN), 4: ("calc", FMT_YEN_DEC),
                                  5: ("calc", FMT_YEN_DEC), 6: ("calc", FMT_PCT), 7: ("calc", FMT_YEN_DEC),
                                  8: ("calc", None), 9: ("input", None)})
    ws.conditional_formatting.add(f"H{first}:H{last}", CellIsRule(operator="notEqual", formula=['"OK"'],
                                                               fill=PatternFill("solid", fgColor=C_WARN)))
    ws.freeze_panes = "B4"
    if sample:
        for i, (name, cat, price) in enumerate(SAMPLE_PRODUCTS):
            r = first + i
            ws.cell(row=r, column=1, value=name)
            ws.cell(row=r, column=2, value=cat)
            ws.cell(row=r, column=3, value=price)


def build_expense_master(wb):
    ws = wb.create_sheet(S_EXM)
    title(ws, "費目マスタ", "P&L区分で損益計算書のどこに入るかが決まります。空欄行に費目を追加できます。")
    header(ws, 3, ["費目", "P&L区分", "既定税率", "説明・例"], [20, 12, 10, 70])
    first, last = 4, 3 + N_EXPENSE_MASTER
    for i, (name, kind, tax, desc) in enumerate(EXPENSE_ITEMS):
        r = first + i
        ws.cell(row=r, column=1, value=name)
        ws.cell(row=r, column=2, value=kind)
        ws.cell(row=r, column=3, value=tax)
        ws.cell(row=r, column=4, value=desc)
    style_range(ws, first, last, {1: ("input", None), 2: ("input", None), 3: ("input", FMT_PCT), 4: ("input", None)})
    add_list_validation(ws, '"売上原価,変動費,固定費"', f"B{first}:B{last}")
    ws.cell(row=last + 2, column=1, value="※ 減価償却費は『設備』シートから自動計上されるため、費目に追加しないでください。").font = F_NOTE
    ws.freeze_panes = "A4"


def build_equipment(wb, fy_start: dt.date, sample: bool):
    ws = wb.create_sheet(S_EQP)
    title(ws, "設備（減価償却）", "資産計上した設備を登録すると、取得月から耐用年数の間、月額償却費を該当チャネルの固定費に計上します（定額法・残存価額なしの簡易計算）。")
    header(ws, 3, ["設備名", "チャネル", "取得日", "取得価額\n(税抜)", "耐用年数\n(年)", "月額償却費", "償却終了日", "メモ"],
           [26, 14, 12, 14, 10, 13, 13, 40])
    first, last = 4, 3 + N_EQUIP
    for r in range(first, last + 1):
        ws.cell(row=r, column=6, value=f'=IF(OR(D{r}="",E{r}="",E{r}=0),"",ROUND(D{r}/(E{r}*12),0))')
        ws.cell(row=r, column=7, value=f'=IF(OR(C{r}="",E{r}=""),"",EDATE(C{r},E{r}*12)-1)')
    style_range(ws, first, last, {1: ("input", None), 2: ("input", None), 3: ("input", FMT_DATE), 4: ("input", FMT_YEN),
                                  5: ("input", '0'), 6: ("calc", FMT_YEN), 7: ("calc", FMT_DATE), 8: ("input", None)})
    add_list_validation(ws, f"{q(S_SET)}$A${SET_CH_ROW0}:$A${SET_CH_ROW0 + 3}", f"B{first}:B{last}")
    ws.cell(row=last + 2, column=1,
            value="※ 耐用年数・少額減価償却資産の特例などの税務判断は税理士にご確認ください。ここは月次の管理会計用の概算です。").font = F_NOTE
    ws.freeze_panes = "A4"
    if sample:
        data = [
            ("クレープ焼き機（2台）", "店舗", fy_start, 600000, 5, "（サンプル）"),
            ("業務用冷蔵庫", "店舗", fy_start, 400000, 6, "（サンプル）"),
            ("キッチンカー車両・内装", "キッチンカー", fy_start, 3000000, 4, "（サンプル）"),
            ("冷蔵自販機", "自販機", fy_start, 1500000, 5, "（サンプル）"),
        ]
        for i, row in enumerate(data):
            for c, v in enumerate(row, start=1):
                if c == 6:
                    c = 8
                ws.cell(row=first + i, column=c, value=v)


def build_sales(wb, fy_start: dt.date, sample: bool):
    ws = wb.create_sheet(S_SAL)
    title(ws, "売上入力", "1行＝日付×チャネル×商品。単価は商品マスタから自動取得（割引価格などは『単価上書き』に入力）。")
    header(ws, 3, ["日付", "チャネル", "販売区分", "商品名", "販売数", "廃棄数", "値引額\n(税込)", "単価上書き\n(税込)",
                   "適用単価\n(税込)", "売上\n(税込)", "税率", "売上\n(税抜)", "材料原価\n(理論)", "廃棄原価"],
           [12, 13, 11, 26, 9, 9, 11, 11, 11, 12, 8, 12, 12, 11])
    first, last = 4, 3 + N_SALES
    prd = f"{q(S_PRD)}$A:$D"
    std = f"{q(S_SET)}{SET_TAX_STD}"
    red = f"{q(S_SET)}{SET_TAX_RED}"
    for r in range(first, last + 1):
        ws.cell(row=r, column=9, value=f'=IF(D{r}="","",IF(H{r}<>"",H{r},IFERROR(VLOOKUP(D{r},{prd},3,FALSE),0)))')
        ws.cell(row=r, column=10, value=f'=IF(D{r}="","",N(E{r})*I{r}-N(G{r}))')
        ws.cell(row=r, column=11, value=f'=IF(D{r}="","",IF(C{r}="イートイン",{std},{red}))')
        ws.cell(row=r, column=12, value=f'=IF(D{r}="","",ROUND(J{r}/(1+K{r}),0))')
        ws.cell(row=r, column=13, value=f'=IF(D{r}="","",N(E{r})*IFERROR(VLOOKUP(D{r},{prd},4,FALSE),0))')
        ws.cell(row=r, column=14, value=f'=IF(D{r}="","",N(F{r})*IFERROR(VLOOKUP(D{r},{prd},4,FALSE),0))')
    style_range(ws, first, last, {1: ("input", FMT_DATE), 2: ("input", None), 3: ("input", None), 4: ("input", None),
                                  5: ("input", FMT_NUM), 6: ("input", FMT_NUM), 7: ("input", FMT_YEN), 8: ("input", FMT_YEN),
                                  9: ("calc", FMT_YEN), 10: ("calc", FMT_YEN), 11: ("calc", '0%'), 12: ("calc", FMT_YEN),
                                  13: ("calc", FMT_YEN), 14: ("calc", FMT_YEN)})
    add_list_validation(ws, f"{q(S_SET)}$A${SET_CH_ROW0}:$A${SET_CH_ROW0 + 2}", f"B{first}:B{last}")
    add_list_validation(ws, '"持ち帰り,イートイン"', f"C{first}:C{last}")
    add_list_validation(ws, f"{q(S_PRD)}$A$4:$A${3 + N_PRODUCT}", f"D{first}:D{last}")
    ws.freeze_panes = "A4"
    if sample:
        rnd = random.Random(42)
        r = first
        day = fy_start
        end = (fy_start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)  # 翌月1日
        end = (end.replace(day=28) + dt.timedelta(days=4)).replace(day=1)  # 2か月分
        while day < end:
            wd = day.weekday()
            # 店舗：水曜定休
            if wd != 2:
                for name, base in [("バナナチョコ生クリーム", 18), ("いちご生クリーム", 14), ("カスタードバナナ", 9), ("ツナチーズ", 6)]:
                    k = 1.6 if wd >= 5 else 1.0
                    qty = max(0, int(rnd.gauss(base * k, base * 0.2)))
                    eat = "イートイン" if rnd.random() < 0.2 else "持ち帰り"
                    ws.cell(row=r, column=1, value=day); ws.cell(row=r, column=2, value="店舗")
                    ws.cell(row=r, column=3, value=eat); ws.cell(row=r, column=4, value=name)
                    ws.cell(row=r, column=5, value=qty)
                    r += 1
            # キッチンカー：土日のみ
            if wd >= 5:
                for name, base in [("バナナチョコ生クリーム", 35), ("いちご生クリーム", 25), ("ツナチーズ", 12)]:
                    qty = max(0, int(rnd.gauss(base, base * 0.25)))
                    ws.cell(row=r, column=1, value=day); ws.cell(row=r, column=2, value="キッチンカー")
                    ws.cell(row=r, column=3, value="持ち帰り"); ws.cell(row=r, column=4, value=name)
                    ws.cell(row=r, column=5, value=qty)
                    r += 1
            # 自販機：毎日
            qty = max(0, int(rnd.gauss(8, 2)))
            ws.cell(row=r, column=1, value=day); ws.cell(row=r, column=2, value="自販機")
            ws.cell(row=r, column=3, value="持ち帰り"); ws.cell(row=r, column=4, value="冷やしクレープ（自販機）")
            ws.cell(row=r, column=5, value=qty)
            ws.cell(row=r, column=6, value=rnd.choice([0, 0, 0, 1, 2]))
            r += 1
            day += dt.timedelta(days=1)


def build_expenses(wb, fy_start: dt.date, sample: bool):
    ws = wb.create_sheet(S_EXP)
    title(ws, "経費入力", "税込金額で入力。税率が空欄なら費目マスタの既定税率で税抜換算します。チャネル不明の経費は『共通』。")
    header(ws, 3, ["日付", "費目", "チャネル", "支払先", "摘要", "金額\n(税込)", "税率\n(空欄=既定)", "金額\n(税抜)", "P&L区分"],
           [12, 16, 13, 18, 30, 13, 11, 13, 11])
    first, last = 4, 3 + N_EXPENSE
    exm = f"{q(S_EXM)}$A:$C"
    for r in range(first, last + 1):
        ws.cell(row=r, column=8,
                value=f'=IF(F{r}="","",ROUND(F{r}/(1+IF(G{r}="",IFERROR(VLOOKUP(B{r},{exm},3,FALSE),0),G{r})),0))')
        ws.cell(row=r, column=9, value=f'=IF(B{r}="","",IFERROR(VLOOKUP(B{r},{exm},2,FALSE),"未登録"))')
    style_range(ws, first, last, {1: ("input", FMT_DATE), 2: ("input", None), 3: ("input", None), 4: ("input", None),
                                  5: ("input", None), 6: ("input", FMT_YEN), 7: ("input", '0%'), 8: ("calc", FMT_YEN),
                                  9: ("calc", None)})
    add_list_validation(ws, f"{q(S_EXM)}$A$4:$A${3 + N_EXPENSE_MASTER}", f"B{first}:B{last}")
    add_list_validation(ws, f"{q(S_SET)}$A${SET_CH_ROW0}:$A${SET_CH_ROW0 + 3}", f"C{first}:C{last}")
    ws.conditional_formatting.add(f"I{first}:I{last}", CellIsRule(operator="equal", formula=['"未登録"'],
                                                               fill=PatternFill("solid", fgColor=C_WARN)))
    ws.freeze_panes = "A4"
    if sample:
        rows = []
        for m in range(2):
            y, mo = fy_start.year + (fy_start.month - 1 + m) // 12, (fy_start.month - 1 + m) % 12 + 1
            d = lambda day: dt.date(y, mo, day)  # noqa: E731
            rows += [
                (d(5), "材料仕入", "店舗", "食材卸（サンプル）", "食材", 260000, None),
                (d(5), "包材仕入", "店舗", "包材店（サンプル）", "包み紙", 8000, None),
                (d(6), "材料仕入", "キッチンカー", "食材卸（サンプル）", "食材", 110000, None),
                (d(6), "材料仕入", "自販機", "食材卸（サンプル）", "食材", 45000, None),
                (d(6), "包材仕入", "自販機", "包材店（サンプル）", "容器・ラベル", 12000, None),
                (d(25), "人件費", "店舗", "", "アルバイト給与", 380000, None),
                (d(25), "人件費", "キッチンカー", "", "アルバイト給与", 120000, None),
                (d(25), "人件費", "自販機", "", "補充スタッフ", 30000, None),
                (d(27), "家賃", "店舗", "家主（サンプル）", "店舗家賃", 198000, None),
                (d(27), "駐車場代", "キッチンカー", "月極（サンプル）", "保管場所", 22000, None),
                (d(20), "水道光熱費", "店舗", "電力会社等", "電気・ガス・水道", 55000, None),
                (d(20), "水道光熱費", "自販機", "設置先", "自販機電気代", 6600, None),
                (d(28), "自販機設置手数料", "自販機", "設置先", "売上歩合", 15000, None),
                (d(28), "出店料", "キッチンカー", "イベント主催者", "出店料", 40000, None),
                (d(28), "燃料費", "キッチンカー", "GS", "ガソリン・ガス", 18000, None),
                (d(28), "決済手数料", "店舗", "決済代行", "キャッシュレス手数料", 9000, None),
                (d(28), "消耗品費", "店舗", "ホームセンター", "手袋・洗剤", 7000, None),
                (d(15), "販促費", "店舗", "印刷会社", "チラシ", 22000, None),
                (d(15), "通信費", COMMON, "通信会社", "ネット・POS月額", 11000, None),
                (d(15), "支払報酬", COMMON, "会計事務所", "顧問料", 33000, None),
                (d(15), "保険料", COMMON, "保険会社", "PL保険・車両保険", 15000, None),
            ]
        for i, row in enumerate(rows):
            for c, v in enumerate(row, start=1):
                if v is not None:
                    ws.cell(row=first + i, column=c if c < 7 else 7, value=v)


def build_stock(wb, fy_start: dt.date, sample: bool):
    ws = wb.create_sheet(S_STK)
    title(ws, "棚卸（月末在庫）", "月末に残っている材料・包材を税抜金額で入力。日付はその月の月末日（同じ月内の日付ならOK）。期首（開業時）在庫は前月末として入力。")
    header(ws, 3, ["棚卸日\n(月末)", "チャネル", "在庫金額\n(税抜)", "メモ"], [13, 14, 14, 40])
    first, last = 4, 3 + N_STOCK
    style_range(ws, first, last, {1: ("input", FMT_DATE), 2: ("input", None), 3: ("input", FMT_YEN), 4: ("input", None)})
    add_list_validation(ws, f"{q(S_SET)}$A${SET_CH_ROW0}:$A${SET_CH_ROW0 + 2}", f"B{first}:B{last}")
    ws.freeze_panes = "A4"
    if sample:
        def month_end(d: dt.date) -> dt.date:
            return (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        m0 = fy_start
        m1 = month_end(m0) + dt.timedelta(days=1)
        r = first
        for d, vals in [(m0 - dt.timedelta(days=1), (30000, 10000, 5000)),
                        (month_end(m0), (35000, 12000, 6000)),
                        (month_end(m1), (32000, 9000, 5000))]:
            for ch, v in zip(CHANNELS, vals):
                ws.cell(row=r, column=1, value=d)
                ws.cell(row=r, column=2, value=ch)
                ws.cell(row=r, column=3, value=v)
                ws.cell(row=r, column=4, value="（サンプル）")
                r += 1


# ---------------------------------------------------------------------------
# 月次損益
# ---------------------------------------------------------------------------
def build_monthly_pl(wb):
    ws = wb.create_sheet(S_PL)
    title(ws, "月次損益（チャネル別）", "設定シートの『月次損益で表示する月』を変えると切り替わります。金額はすべて税抜。")
    ws.column_dimensions["A"].width = 34
    for c in "BCDEF":
        ws.column_dimensions[c].width = 15
    ws.column_dimensions["G"].width = 48

    ws["A3"] = "対象月"
    style_cell(ws["A3"], kind="sub", bold=True)
    ws["B3"] = f"={q(S_SET)}{SET_MONTH}"
    style_cell(ws["B3"], kind="total", fmt=FMT_MONTH, bold=True)
    ws["C3"] = "月初"
    ws["D3"] = "=DATE(YEAR(B3),MONTH(B3),1)"
    ws["E3"] = "月末"
    ws["F3"] = "=EOMONTH(D3,0)"
    for a in ("C3", "E3"):
        style_cell(ws[a], kind="sub")
    for a in ("D3", "F3"):
        style_cell(ws[a], kind="calc", fmt=FMT_DATE)
    MS, ME = "$D$3", "$F$3"
    PREV_S, PREV_E = "EDATE($D$3,-1)", "$D$3-1"

    hdr_row = 5
    labels = ["項目"] + [f"={ch_cell(i)}" for i in range(4)] + ["合計", "説明"]
    for c, v in enumerate(labels, start=1):
        cell = ws.cell(row=hdr_row, column=c, value=v)
        cell.font = F_HEAD
        cell.fill = FILL_HEAD
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "B6"

    cols = ["B", "C", "D", "E"]  # 店舗, KC, 自販機, 共通
    sal_date, sal_ch = col_ref(S_SAL, "A"), col_ref(S_SAL, "B")
    exp_date, exp_item, exp_ch, exp_amt, exp_kind = (col_ref(S_EXP, x) for x in "ABCHI")
    stk_date, stk_ch, stk_amt = (col_ref(S_STK, x) for x in "ABC")
    eqp_ch, eqp_start, eqp_amt, eqp_end = (col_ref(S_EQP, x) for x in "BCFG")

    def sales_sum(col: str, ch: str) -> str:
        return f'SUMIFS({col_ref(S_SAL, col)},{sal_ch},{ch}$5,{sal_date},">="&{MS},{sal_date},"<="&{ME})'

    def exp_by_item(item_ref: str, ch: str) -> str:
        return (f'SUMIFS({exp_amt},{exp_item},{item_ref},{exp_ch},{ch}$5,'
                f'{exp_date},">="&{MS},{exp_date},"<="&{ME})')

    def exp_by_kind(kind: str, ch: str) -> str:
        return (f'SUMIFS({exp_amt},{exp_kind},"{kind}",{exp_ch},{ch}$5,'
                f'{exp_date},">="&{MS},{exp_date},"<="&{ME})')

    def stock(ch: str, s: str, e: str) -> str:
        return f'SUMIFS({stk_amt},{stk_ch},{ch}$5,{stk_date},">="&{s},{stk_date},"<="&{e})'

    row = hdr_row + 1
    refs: dict[str, int] = {}

    def put(key: str | None, label: str, per_ch, *, total="sum", fmt=FMT_YEN, kind="calc", note="",
            common_value=None, bold=False):
        nonlocal row
        style_cell(ws.cell(row=row, column=1, value=label), kind="sub" if kind != "total" else "total", bold=bold or kind == "total")
        for i, col in enumerate(cols):
            if i == 3 and common_value is not None:
                v = common_value(row) if callable(common_value) else common_value
            else:
                v = per_ch(col, row) if per_ch else None
            c = ws.cell(row=row, column=2 + i, value=v)
            style_cell(c, kind=kind, fmt=fmt, bold=bold)
        if total == "sum":
            tv = f"=SUM(B{row}:E{row})"
        elif callable(total):
            tv = total(row)
        else:
            tv = total
        style_cell(ws.cell(row=row, column=6, value=tv), kind="total" if kind == "total" else "calc", fmt=fmt, bold=True)
        ws.cell(row=row, column=7, value=note).font = F_NOTE
        if key:
            refs[key] = row
        row += 1

    def section(label: str):
        nonlocal row
        for c in range(1, 7):
            cell = ws.cell(row=row, column=c, value=label if c == 1 else None)
            cell.fill = FILL_SUB
            cell.font = F_BOLD
            cell.border = BORDER
        row += 1

    # --- 売上 ---
    section("■ 売上")
    put("sales", "売上高（税抜）", lambda c, r: f"={sales_sum('L', c)}", common_value=0, kind="total",
        note="売上入力の税抜売上")
    put("qty", "販売数（個）", lambda c, r: f"={sales_sum('E', c)}", common_value=0, fmt=FMT_NUM)
    put("waste_qty", "廃棄数（個）", lambda c, r: f"={sales_sum('F', c)}", common_value=0, fmt=FMT_NUM)
    put("unit", "1個あたり売上（税抜）",
        lambda c, r: f'=IFERROR({c}{refs["sales"]}/{c}{refs["qty"]},0)', common_value="",
        total=lambda r: f'=IFERROR(F{refs["sales"]}/F{refs["qty"]},0)', fmt=FMT_YEN)

    # --- 売上原価 ---
    section("■ 売上原価")
    put("open", "期首在庫（前月末棚卸）", lambda c, r: f"={stock(c, PREV_S, PREV_E)}", common_value=0)
    put("buy", "材料・包材仕入", lambda c, r: f"={exp_by_kind('売上原価', c)}",
        note="経費入力のP&L区分＝売上原価")
    put("close", "期末在庫（当月末棚卸）", lambda c, r: f"={stock(c, MS, ME)}", common_value=0)
    put("cogs", "売上原価", lambda c, r: f"={c}{refs['open']}+{c}{refs['buy']}-{c}{refs['close']}", kind="total",
        note="期首在庫＋仕入−期末在庫")
    put("gross", "粗利（売上総利益）", lambda c, r: f"={c}{refs['sales']}-{c}{refs['cogs']}", kind="total")
    put("gross_rate", "粗利率", lambda c, r: f'=IFERROR({c}{refs["gross"]}/{c}{refs["sales"]},"-")',
        total=lambda r: f'=IFERROR(F{refs["gross"]}/F{refs["sales"]},"-")', fmt=FMT_PCT)

    exm = q(S_EXM)
    var_rows = [(i, it) for i, it in enumerate(EXPENSE_ITEMS) if it[1] == "変動費"]
    fix_rows = [(i, it) for i, it in enumerate(EXPENSE_ITEMS) if it[1] == "固定費"]

    # --- 変動費 ---
    section("■ 変動費（売上に比例する経費）")
    for i, it in var_rows:
        mref = f"{exm}$A${4 + i}"
        style_cell(ws.cell(row=row, column=1), kind="sub")
        put(None, "", lambda c, r, m=mref: f"={exp_by_item(m, c)}")
        ws.cell(row=row - 1, column=1, value=f"={mref}")
        ws.cell(row=row - 1, column=1).alignment = Alignment(indent=1)
    put("var", "変動費 計", lambda c, r: f"={exp_by_kind('変動費', c)}", kind="total",
        note="費目マスタで変動費に区分された全費目の合計")
    put("margin", "限界利益", lambda c, r: f"={c}{refs['gross']}-{c}{refs['var']}", kind="total",
        note="粗利−変動費。固定費を回収する原資")

    # --- 固定費 ---
    section("■ 固定費")
    labor_row = None
    for i, it in fix_rows:
        mref = f"{exm}$A${4 + i}"
        put(None, "", lambda c, r, m=mref: f"={exp_by_item(m, c)}")
        ws.cell(row=row - 1, column=1, value=f"={mref}")
        ws.cell(row=row - 1, column=1).alignment = Alignment(indent=1)
        if it[0] == "人件費":
            labor_row = row - 1
    put("dep", "減価償却費（設備シート）",
        lambda c, r: f'=SUMIFS({eqp_amt},{eqp_ch},{c}$5,{eqp_start},"<="&{ME},{eqp_end},">="&{MS})',
        note="取得日〜償却終了日の期間中のみ計上")
    put("fix", "固定費 計", lambda c, r: f"={exp_by_kind('固定費', c)}+{c}{refs['dep']}", kind="total")
    put("direct", "チャネル貢献利益", lambda c, r: f"={c}{refs['margin']}-{c}{refs['fix']}", kind="total",
        note="共通費を配賦する前の、各チャネルが稼いだ利益")

    # --- 共通費配賦 ---
    section("■ 共通費の配賦")
    alloc = f"{q(S_SET)}{SET_ALLOC}"

    def rate_formula(c, r):
        i = cols.index(c)
        return (f'=IF({alloc}="手入力",{ch_rate(i)},'
                f'IFERROR({c}{refs["sales"]}/SUM($B${refs["sales"]}:$D${refs["sales"]}),0))')

    put("rate", "配賦率", rate_formula, common_value="", fmt=FMT_PCT, total=lambda r: f"=SUM(B{r}:D{r})",
        note="設定シートの配賦方法（売上比／手入力）")
    put("alloc", "共通費配賦額", lambda c, r: f"=-$E${refs['direct']}*{c}{refs['rate']}",
        common_value=lambda r: f"=E{refs['direct']}",
        note="共通列のマイナス（共通費）を各チャネルへ振り替え。合計は0になります")
    put("op", "営業利益", lambda c, r: f"={c}{refs['direct']}-{c}{refs['alloc']}", kind="total", bold=True)
    put("op_rate", "営業利益率", lambda c, r: f'=IFERROR({c}{refs["op"]}/{c}{refs["sales"]},"-")',
        common_value="", total=lambda r: f'=IFERROR(F{refs["op"]}/F{refs["sales"]},"-")', fmt=FMT_PCT)

    # --- KPI ---
    section("■ 経営指標（KPI）")
    s = refs["sales"]
    put("cost_rate", "原価率（実際）", lambda c, r: f'=IFERROR({c}{refs["cogs"]}/{c}{s},"-")', common_value="",
        total=lambda r: f'=IFERROR(F{refs["cogs"]}/F{s},"-")', fmt=FMT_PCT, note="売上原価÷売上")
    put("theory", "理論原価（レシピ×販売数）", lambda c, r: f"={sales_sum('M', c)}", common_value=0,
        note="レシピどおりに作った場合の材料原価")
    put("theory_rate", "原価率（理論）", lambda c, r: f'=IFERROR({c}{refs["theory"]}/{c}{s},"-")', common_value="",
        total=lambda r: f'=IFERROR(F{refs["theory"]}/F{s},"-")', fmt=FMT_PCT)
    put("gap", "原価差異（実際−理論）", lambda c, r: f"={c}{refs['cogs']}-{c}{refs['theory']}", common_value=0,
        note="プラスが大きい＝廃棄・盛りすぎ・記録漏れ・仕入値上がりの可能性")
    put("waste", "廃棄原価", lambda c, r: f"={sales_sum('N', c)}", common_value=0)
    if labor_row:
        put("labor_rate", "人件費率", lambda c, r: f'=IFERROR({c}{labor_row}/{c}{s},"-")', common_value="",
            total=lambda r: f'=IFERROR(F{labor_row}/F{s},"-")', fmt=FMT_PCT)
        put("fl", "FL比率（原価＋人件費）", lambda c, r: f'=IFERROR(({c}{refs["cogs"]}+{c}{labor_row})/{c}{s},"-")',
            common_value="", total=lambda r: f'=IFERROR((F{refs["cogs"]}+F{labor_row})/F{s},"-")', fmt=FMT_PCT,
            note="飲食業の代表的な効率指標")

    def bep(c):
        return (f'IFERROR(({c}{refs["fix"]}+{c}{refs["alloc"]})/'
                f'(1-({c}{refs["cogs"]}+{c}{refs["var"]})/{c}{s}),"-")')

    put("bep", "損益分岐点売上（共通費配賦後）", lambda c, r: f"={bep(c)}", common_value="",
        total=lambda r: f'=IFERROR(F{refs["fix"]}/(1-(F{refs["cogs"]}+F{refs["var"]})/F{s}),"-")',
        note="固定費÷限界利益率")
    put("bep_qty", "損益分岐点販売数（個/月）",
        lambda c, r: f'=IFERROR({c}{refs["bep"]}/{c}{refs["unit"]},"-")', common_value="",
        total=lambda r: f'=IFERROR(F{refs["bep"]}/F{refs["unit"]},"-")', fmt=FMT_NUM)
    put("safety", "安全余裕率", lambda c, r: f'=IFERROR(({c}{s}-{c}{refs["bep"]})/{c}{s},"-")', common_value="",
        total=lambda r: f'=IFERROR((F{s}-F{refs["bep"]})/F{s},"-")', fmt=FMT_PCT,
        note="売上があと何％落ちると赤字になるか")
    tgt = f"{q(S_SET)}{SET_TARGET}"
    put("need_qty", "目標営業利益に必要な販売数（個/月）", None, common_value="",
        total=lambda r: (f'=IFERROR((F{refs["fix"]}+{tgt})/(F{refs["margin"]}/F{refs["qty"]}),"-")'),
        fmt=FMT_NUM, note="（固定費＋目標利益）÷1個あたり限界利益。合計列のみ")

    # --- チェック ---
    section("■ 入力チェック（0なら正常）")
    total_exp = (f'SUMIFS({exp_amt},{exp_date},">="&{MS},{exp_date},"<="&{ME})')
    put("check", "経費入力の当月合計 − 損益計上額", None, common_value="",
        total=lambda r: (f'={total_exp}-(F{refs["buy"]}+F{refs["var"]}+F{refs["fix"]}-F{refs["dep"]})'),
        note="0以外＝費目またはチャネルが未登録・空欄の経費があります")
    ws.conditional_formatting.add(f"F{refs['check']}", CellIsRule(operator="notEqual", formula=["0"],
                                                                 fill=PatternFill("solid", fgColor=C_WARN)))
    ws.conditional_formatting.add(f"B{refs['op']}:F{refs['op']}", CellIsRule(operator="lessThan", formula=["0"],
                                                                            fill=PatternFill("solid", fgColor=C_WARN)))
    return refs


# ---------------------------------------------------------------------------
# 年間推移
# ---------------------------------------------------------------------------
def build_yearly(wb):
    ws = wb.create_sheet(S_YR)
    title(ws, "年間推移", "設定シートの『事業年度の開始日』から12か月。金額は税抜。共通費を含む全社合計の損益です。")
    labels = ["月", "店舗\n売上", "キッチンカー\n売上", "自販機\n売上", "売上合計", "販売数", "売上原価", "粗利",
              "粗利率", "変動費", "固定費\n(償却含む)", "営業利益", "営業利益率", "原価率", "累計\n営業利益"]
    header(ws, 4, labels, [11, 13, 13, 13, 13, 10, 13, 13, 9, 12, 13, 13, 10, 9, 14])
    ws.cell(row=4, column=2, value=f'={ch_cell(0)}&"売上"')
    ws.cell(row=4, column=3, value=f'={ch_cell(1)}&"売上"')
    ws.cell(row=4, column=4, value=f'={ch_cell(2)}&"売上"')
    ws.freeze_panes = "B5"
    sal_date, sal_ch, sal_amt, sal_qty = (col_ref(S_SAL, x) for x in "ABLE")
    exp_date, exp_amt, exp_kind = (col_ref(S_EXP, x) for x in "AHI")
    stk_date, stk_amt = col_ref(S_STK, "A"), col_ref(S_STK, "C")
    eqp_start, eqp_amt, eqp_end = (col_ref(S_EQP, x) for x in "CFG")
    first = 5
    for k in range(12):
        r = first + k
        ws.cell(row=r, column=1, value=f"={q(S_SET)}{SET_FY}" if k == 0 else f"=EDATE(A{r - 1},1)")
        ms = f"DATE(YEAR($A{r}),MONTH($A{r}),1)"
        me = f"EOMONTH($A{r},0)"
        for j in range(3):
            col = get_column_letter(2 + j)
            ws.cell(row=r, column=2 + j,
                    value=f'=SUMIFS({sal_amt},{sal_ch},{ch_cell(j)},{sal_date},">="&{ms},{sal_date},"<="&{me})')
        ws.cell(row=r, column=5, value=f"=SUM(B{r}:D{r})")
        ws.cell(row=r, column=6, value=f'=SUMIFS({sal_qty},{sal_date},">="&{ms},{sal_date},"<="&{me})')
        prev_s, prev_e = f"EDATE({ms},-1)", f"{ms}-1"
        ws.cell(row=r, column=7, value=(
            f'=SUMIFS({stk_amt},{stk_date},">="&{prev_s},{stk_date},"<="&{prev_e})'
            f'+SUMIFS({exp_amt},{exp_kind},"売上原価",{exp_date},">="&{ms},{exp_date},"<="&{me})'
            f'-SUMIFS({stk_amt},{stk_date},">="&{ms},{stk_date},"<="&{me})'))
        ws.cell(row=r, column=8, value=f"=E{r}-G{r}")
        ws.cell(row=r, column=9, value=f'=IFERROR(H{r}/E{r},"-")')
        ws.cell(row=r, column=10, value=f'=SUMIFS({exp_amt},{exp_kind},"変動費",{exp_date},">="&{ms},{exp_date},"<="&{me})')
        ws.cell(row=r, column=11, value=(
            f'=SUMIFS({exp_amt},{exp_kind},"固定費",{exp_date},">="&{ms},{exp_date},"<="&{me})'
            f'+SUMIFS({eqp_amt},{eqp_start},"<="&{me},{eqp_end},">="&{ms})'))
        ws.cell(row=r, column=12, value=f"=H{r}-J{r}-K{r}")
        ws.cell(row=r, column=13, value=f'=IFERROR(L{r}/E{r},"-")')
        ws.cell(row=r, column=14, value=f'=IFERROR(G{r}/E{r},"-")')
        ws.cell(row=r, column=15, value=f"=L{r}" if k == 0 else f"=O{r - 1}+L{r}")
    last = first + 11
    fmts = {1: ("calc", FMT_MONTH), 2: ("calc", FMT_YEN), 3: ("calc", FMT_YEN), 4: ("calc", FMT_YEN),
            5: ("calc", FMT_YEN), 6: ("calc", FMT_NUM), 7: ("calc", FMT_YEN), 8: ("calc", FMT_YEN), 9: ("calc", FMT_PCT),
            10: ("calc", FMT_YEN), 11: ("calc", FMT_YEN), 12: ("calc", FMT_YEN), 13: ("calc", FMT_PCT),
            14: ("calc", FMT_PCT), 15: ("calc", FMT_YEN)}
    style_range(ws, first, last, fmts)
    tr = last + 1
    ws.cell(row=tr, column=1, value="年間合計")
    for c in range(2, 13):
        L = get_column_letter(c)
        ws.cell(row=tr, column=c, value=f"=SUM({L}{first}:{L}{last})")
    ws.cell(row=tr, column=9, value=f'=IFERROR(H{tr}/E{tr},"-")')
    ws.cell(row=tr, column=13, value=f'=IFERROR(L{tr}/E{tr},"-")')
    ws.cell(row=tr, column=14, value=f'=IFERROR(G{tr}/E{tr},"-")')
    ws.cell(row=tr, column=15, value=f"=O{last}")
    for c in range(1, 16):
        style_cell(ws.cell(row=tr, column=c), kind="total", fmt=fmts[c][1] if c > 1 else None, bold=True)
    ws.conditional_formatting.add(f"L{first}:L{tr}", CellIsRule(operator="lessThan", formula=["0"],
                                                               fill=PatternFill("solid", fgColor=C_WARN)))
    # ※ 年間推移の売上原価は棚卸の入力がない月は「仕入＝原価」として扱われる旨を注記
    ws.cell(row=tr + 2, column=1,
            value="※ 棚卸を入力していない月は『仕入額＝売上原価』になります。月末棚卸を入力すると精度が上がります。").font = F_NOTE

    chart = BarChart()
    chart.type = "col"
    chart.grouping = "stacked"
    chart.overlap = 100
    chart.title = "チャネル別売上と営業利益"
    chart.y_axis.title = "円（税抜）"
    data = Reference(ws, min_col=2, max_col=4, min_row=4, max_row=last)
    cats = Reference(ws, min_col=1, min_row=first, max_row=last)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(cats)
    line = LineChart()
    line.add_data(Reference(ws, min_col=12, max_col=12, min_row=4, max_row=last), titles_from_data=True)
    chart += line
    chart.height = 9
    chart.width = 24
    ws.add_chart(chart, f"A{tr + 4}")


# ---------------------------------------------------------------------------
# シミュレーション
# ---------------------------------------------------------------------------
def build_simulation(wb, sample: bool):
    ws = wb.create_sheet(S_SIM)
    title(ws, "シミュレーション", "黄色セルを変えて試算します。実績データとは連動しない『試算用』シートです（結果は想定値）。")
    ws.column_dimensions["A"].width = 30
    for c in "BCDEFGH":
        ws.column_dimensions[c].width = 13

    # --- 1. 価格×原価 → 原価率表 ---
    ws["A3"] = "① 販売価格（税込）× 材料原価 → 原価率（持ち帰り・軽減税率で税抜換算）"
    ws["A3"].font = F_BOLD
    ws["A4"] = "材料原価（円/個）＼販売価格（税込）"
    style_cell(ws["A4"], kind="sub", bold=True)
    prices = [650, 700, 750, 800]
    costs = [120, 150, 180, 210, 240, 270, 300]
    red = f"{q(S_SET)}{SET_TAX_RED}"
    for j, p in enumerate(prices):
        style_cell(ws.cell(row=4, column=2 + j, value=p), kind="input", fmt=FMT_YEN, bold=True)
    for i, cst in enumerate(costs):
        r = 5 + i
        style_cell(ws.cell(row=r, column=1, value=cst), kind="input", fmt=FMT_YEN, bold=True)
        for j in range(len(prices)):
            L = get_column_letter(2 + j)
            c = ws.cell(row=r, column=2 + j, value=f"=IFERROR($A{r}/({L}$4/(1+{red})),\"-\")")
            style_cell(c, kind="calc", fmt=FMT_PCT)
    ws.conditional_formatting.add(f"B5:E{4 + len(costs)}",
                                  CellIsRule(operator="greaterThan", formula=[f"{red.replace('$B$7', '$B$10')}"],
                                             fill=PatternFill("solid", fgColor=C_WARN)))
    ws.cell(row=5 + len(costs), column=1, value="※ 赤色＝設定シートの目標原価率を超える組み合わせ").font = F_NOTE

    # --- 2. 月間損益シミュレーション ---
    base = 15
    ws.cell(row=base, column=1, value="② 月間損益シミュレーション（チャネル別・想定値）").font = F_BOLD
    head = ["項目"] + [f"={ch_cell(i)}" for i in range(3)] + ["合計"]
    for c, v in enumerate(head, start=1):
        cell = ws.cell(row=base + 1, column=c, value=v)
        cell.font = F_HEAD
        cell.fill = FILL_HEAD
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center")
    sample_inputs = {
        "平均販売単価（税込）": [720, 730, 700],
        "1日あたり販売数（個）": [50, 70, 8],
        "月間営業日数（日）": [26, 9, 30],
        "1個あたり材料原価（円）": [190, 190, 230],
        "変動費率（手数料・出店料等）": [0.02, 0.15, 0.20],
        "月間固定費（人件費・家賃・償却等）": [700000, 250000, 60000],
    }
    inputs = list(sample_inputs.keys())
    fmts_in = [FMT_YEN, FMT_NUM, FMT_NUM, FMT_YEN, FMT_PCT, FMT_YEN]
    r0 = base + 2
    for i, label in enumerate(inputs):
        r = r0 + i
        style_cell(ws.cell(row=r, column=1, value=label), kind="sub", bold=True)
        for j in range(3):
            v = sample_inputs[label][j] if sample else None
            style_cell(ws.cell(row=r, column=2 + j, value=v), kind="input", fmt=fmts_in[i])
        style_cell(ws.cell(row=r, column=5, value=""), kind="calc")
    P, Q, D, C, V, F = (r0 + i for i in range(6))
    outs = [
        ("月間販売数（個）", lambda L: f"=N({L}{Q})*N({L}{D})", FMT_NUM, True),
        ("売上高（税抜）", lambda L: f"=N({L}{P})/(1+{red})*N({L}{Q})*N({L}{D})", FMT_YEN, True),
        ("材料原価", lambda L: f"=N({L}{C})*N({L}{Q})*N({L}{D})", FMT_YEN, True),
        ("変動費", lambda L: f"=N({L}{V})*{L}{{sales}}", FMT_YEN, True),
        ("限界利益", lambda L: f"={L}{{sales}}-{L}{{cogs}}-{L}{{var}}", FMT_YEN, True),
        ("固定費", lambda L: f"=N({L}{F})", FMT_YEN, True),
        ("営業利益（想定）", lambda L: f"={L}{{margin}}-{L}{{fix}}", FMT_YEN, True),
        ("原価率", lambda L: f'=IFERROR({L}{{cogs}}/{L}{{sales}},"-")', FMT_PCT, False),
        ("1個あたり限界利益", lambda L: f'=IFERROR({L}{{margin}}/{L}{{qty}},"-")', FMT_YEN_DEC, False),
        ("損益分岐点販売数（個/月）", lambda L: f'=IFERROR({L}{{fix}}/{L}{{unit_m}},"-")', FMT_NUM, False),
        ("損益分岐点販売数（個/日）", lambda L: f'=IFERROR({L}{{bep_m}}/N({L}{D}),"-")', FMT_NUM, False),
    ]
    keys = ["qty", "sales", "cogs", "var", "margin", "fix", "op", "cost_rate", "unit_m", "bep_m", "bep_d"]
    rows = {k: r0 + len(inputs) + 1 + i for i, k in enumerate(keys)}
    for (label, fn, fmt, summable), k in zip(outs, keys):
        r = rows[k]
        kind = "total" if k in ("op",) else "calc"
        style_cell(ws.cell(row=r, column=1, value=label), kind="sub" if kind != "total" else "total", bold=True)
        for j in range(3):
            L = get_column_letter(2 + j)
            f = fn(L).replace("{{", "{").replace("}}", "}").format(**rows) if "{" in fn(L) else fn(L)
            style_cell(ws.cell(row=r, column=2 + j, value=f), kind=kind, fmt=fmt)
        if summable:
            tv = f"=SUM(B{r}:D{r})"
        elif k == "cost_rate":
            tv = f'=IFERROR(E{rows["cogs"]}/E{rows["sales"]},"-")'
        elif k == "unit_m":
            tv = f'=IFERROR(E{rows["margin"]}/E{rows["qty"]},"-")'
        else:
            tv = "―"
        style_cell(ws.cell(row=r, column=5, value=tv), kind="total" if kind == "total" else "calc", fmt=fmt, bold=True)
    note_r = rows["bep_d"] + 2
    ws.cell(row=note_r, column=1,
            value="※ 入力値はすべて仮の想定です。月次損益シートの実績値（1個あたり売上・原価率・固定費）を転記すると精度が上がります。").font = F_NOTE
    if sample:
        ws.cell(row=note_r + 1, column=1, value="※ サンプル値は動作確認用の架空の数値です。").font = F_NOTE


# ---------------------------------------------------------------------------
def build(out: str, *, sample: bool, shop: str, fy_start: dt.date):
    wb = Workbook()
    wb.remove(wb.active)
    month = fy_start
    build_guide(wb, sample)
    build_settings(wb, shop, fy_start, month, sample)
    build_materials(wb, sample)
    build_recipes(wb, sample)
    build_products(wb, sample)
    build_expense_master(wb)
    build_equipment(wb, fy_start, sample)
    build_sales(wb, fy_start, sample)
    build_expenses(wb, fy_start, sample)
    build_stock(wb, fy_start, sample)
    build_monthly_pl(wb)
    build_yearly(wb)
    build_simulation(wb, sample)
    # タブ色
    colors = {S_GUIDE: "7F7F7F", S_SET: "7F7F7F", S_MAT: "BF8F00", S_REC: "BF8F00", S_PRD: "BF8F00",
              S_EXM: "BF8F00", S_EQP: "BF8F00", S_SAL: "2E75B6", S_EXP: "2E75B6", S_STK: "2E75B6",
              S_PL: "548235", S_YR: "548235", S_SIM: "C55A11"}
    for name, color in colors.items():
        wb[name].sheet_properties.tabColor = color
    wb.calculation.fullCalcOnLoad = True
    wb.save(out)
    return out


def main():
    ap = argparse.ArgumentParser(description="クレープ店 収支管理ブックを生成")
    ap.add_argument("--out", required=True, help="出力ファイル（.xlsx）")
    ap.add_argument("--sample", action="store_true", help="動作確認用のサンプル（架空）データを入れる")
    ap.add_argument("--shop", default="（店舗名）", help="店舗名")
    ap.add_argument("--fy-start", default=None, help="事業年度の開始日 YYYY-MM-DD（省略時は今年の1月1日）")
    a = ap.parse_args()
    fy = dt.date.fromisoformat(a.fy_start) if a.fy_start else dt.date(dt.date.today().year, 1, 1)
    print(build(a.out, sample=a.sample, shop=a.shop, fy_start=fy))


if __name__ == "__main__":
    main()
