---
name: nencho-webapp
description: 年末調整（令和8年分）を一元管理するWEBアプリを構築・カスタマイズ・運用するスキル。給与明細PDF（12ヶ月分・賞与）を読み込んで集計シートに入れ、扶養控除等・基礎・配偶者・特定親族・所得金額調整・保険料控除・住宅借入金等特別控除の各申告書から控除額を自動計算し、国税庁「年末調整計算シート（令和８年用）」と同じ①〜㉞の計算シート・源泉徴収簿・確定申告の要否まで自動で出す。Excel出力は元Excelのシート構成とセル番地を踏襲し、集計シート→計算シート、各申告書→計算シートが関数でつながり全シート編集可能。「年末調整」「年調」「源泉徴収簿」「扶養控除等申告書」「保険料控除申告書」「配偶者控除」「給与明細の集計」「年税額の計算」「過不足額の精算」「年末調整計算シート」「keisansheet.xlsm」に関する依頼では、明示的にスキルと言われなくても必ずこのスキルを使うこと。
---

# 年末調整 一元管理WEBアプリ スキル

国税庁の「年末調整計算シート（令和８年用）」（`keisansheet.xlsm`）の仕様を踏襲し、
**給与明細PDF → 集計シート → 各申告書 → 計算シート → 源泉徴収簿／Excel／確定申告チェック** を
1つのWEBアプリで自動連携させます。完成品は `assets/app/` にあり、そのまま動きます。

## このスキルでできること

| 依頼の例 | 対応 |
|---|---|
| 「年末調整のWEBアプリを用意して」 | `assets/app/` を配置し、1ファイル版を `scripts/build_single_html.js` で作る |
| 「給与明細PDFから年税額を計算して」 | アプリの「給与明細取込」を使う。CLIなら `scripts/parse_payslip.py` で抽出し engine で計算 |
| 「社員◯名分の年末調整をまとめたい」 | 従業員一覧（複数人管理・CSV一覧・全員分Excel出力） |
| 「Excel（元の計算シート）と同じ形で出したい」 | 「Excel出力」：13シート・関数連携・保護なし |
| 「来年の税制改正に合わせて更新して」 | `references/annual-update.md` の手順で TABLES と控除テーブルを更新 |
| 「自社の給与明細が読めない」 | `assets/app/js/payslip.js` の `LABELS` にラベルを追加 |

## 構成

```
nencho-webapp/
├── SKILL.md                      ← このファイル
├── assets/app/                   ← WEBアプリ本体（静的ファイルのみ・サーバー不要）
│   ├── index.html
│   ├── css/app.css
│   └── js/
│       ├── engine.js             ← 計算エンジン（令和8年分 TABLES／UMD・Nodeでも動く）
│       ├── payslip.js            ← 給与明細PDFの項目抽出（座標・平文の両対応）
│       ├── workbook.js           ← Excel出力（ExcelJS・関数付き13シート）
│       └── app.js                ← 画面（12タブ・localStorage保存）
├── dist/nencho-app.html          ← 1ファイル版（ダブルクリックで開ける）
├── references/
│   ├── excel-spec.md             ← 元Excelのシート・セル・関数の対応表（必読）
│   ├── tax-rules-r8.md           ← 令和8年分の控除額・改正点（国税庁の出典付き）
│   ├── calc-spec.md              ← ①〜㉞の計算仕様と自動判定ロジック
│   ├── payslip-import.md         ← 給与明細PDF取込の仕様・対応ラベル
│   └── annual-update.md          ← 年度更新・カスタマイズ手順
└── scripts/
    ├── test_engine.js            ← 計算エンジンの単体テスト（境界値＋シナリオ）
    ├── verify_workbook.js        ← Excel関数をLibreOfficeで再計算しエンジンと突合
    ├── e2e_test.js               ← ブラウザ操作テスト（PDF取込〜Excel出力）
    ├── scenarios.js              ← テスト用データ（架空）
    ├── build_single_html.js      ← 1ファイル版のビルド
    └── parse_payslip.py          ← CLI用：給与明細PDF→集計シートJSON/CSV
```

## データの流れ（元Excelとの対応）

```
給与明細PDF ──(payslip.js)──▶ 集計シート（月別12行＋賞与4行）
                                  │ E15→① I15→③ E20→④ I20→⑥ F15+F20→⑫ L列→⑫のうち小規模共済
扶養控除等申告書 ─(年齢・所得・同居で自動区分)─▶ Ⓐ〜Ⓘ → ⑲、特定親族 → ⑱、23歳未満の有無
基礎控除申告書 ─(本人の合計所得＝⑪＋給与以外の所得)─▶ ⑳、区分Ⅰ(A/B/C)
配偶者控除等申告書 ─(区分Ⅰ×配偶者の所得・年齢)─▶ ⑰
所得金額調整控除申告書 ─(特別障害者・23歳未満の扶養親族)─▶ 適用の有無 → ⑩
保険料控除申告書 ─(計算式Ⅰ・Ⅱ・Ⅲ／地震・旧長期)─▶ ⑬⑭⑮⑯
住宅借入金等特別控除申告書 ─▶ ㉔
                                  ▼
                 計算シート ①〜㉞（手入力で上書き可）→ 源泉徴収簿・確定申告チェック・Excel
```

## 作業手順

### 1. アプリを用意する
1. `assets/app/` をそのまま配布するか、`node scripts/build_single_html.js` で `dist/nencho-app.html` を作る。
2. 社内サーバーに置く場合も静的ファイルだけでよい（APIなし）。データは各PCのブラウザ（localStorage）に保存される。
3. 外部ライブラリは cdnjs の pdf.js 3.11.174（PDF取込）と ExcelJS 4.4.0（Excel出力）のみ。オフライン環境ではこの2機能だけ止まり、入力・計算は動く。

### 2. 使い方（担当者向けの説明に使う）
1. 「従業員を追加」→ 基本情報
2. 「給与明細取込」に12ヶ月分＋賞与のPDFをまとめてドロップ → 読取り結果を確認・修正 →「すべて集計シートへ反映」
3. 扶養控除等申告書 → 基礎・配偶者・特定親族・所得金額調整 → 保険料控除 → 住宅借入金等特別控除 を入力
4. 計算シートで①〜㉞を確認。必要な欄は「手入力（上書き）」で修正（空欄に戻すと自動計算）。超過・不足の精算欄 ㉘㉙㉛㉝ を入力
5. 集計シートの「年末調整の過不足税額を12月に記入」→ 源泉徴収簿を印刷 → Excel出力
6. 確定申告チェックで、医療費控除・ふるさと納税・住宅ローン初年度・給与以外の所得20万円超などを確認

### 3. 変更・カスタマイズするとき
- **控除額・税率の変更**は `engine.js` の `TABLES` と `workbook.js` の「控除テーブル」シートの**両方**を直す（`references/annual-update.md`）。
- **画面や項目の追加**は `app.js`（入力は `data-bind="パス"`、表示は `data-out="結果のパス"` で自動連携）。
- **Excelの番地は元ファイルに合わせる**（`references/excel-spec.md`）。番地を変えたら `verify_workbook.js` の `CELL` も直す。

### 4. 変更したら必ず検証する
```bash
node scripts/test_engine.js
```
```bash
npm i exceljs@4.4.0 pdfjs-dist@3.11.174   # 作業用ディレクトリで
```
```bash
EXCELJS=<node_modules>/exceljs node scripts/verify_workbook.js <出力先>
```
```bash
NODE_MODULES=<node_modules> node scripts/e2e_test.js <給与明細PDFのフォルダ> <スクリーンショット出力先>
```
- `verify_workbook.js` は出力Excelを LibreOffice で再計算し、計算シート①〜㉞が engine と一致するかを4シナリオで確認する。
- 不一致が出たら Excel 側の関数か engine のどちらが国税庁の表と違うかを `references/tax-rules-r8.md` で確認してから直す。

## 守ること

- **事実と推定を分ける**：控除額・税率は `references/tax-rules-r8.md` の国税庁出典の値だけを使う。不明な点は国税庁ページ（下記）を確認し、推測で数値を作らない。
- **個人情報**：マイナンバー（個人番号）の入力欄は作らない。データを外部送信する機能を追加しない（サーバー保存にする場合は暗号化・アクセス制御を別途設計し、利用者に確認する）。
- **最終判断は担当者**：アプリは計算と整合チェックを行うが、申告書の受理・記載内容の確認は担当者が行う旨を画面に残す。
- **年末調整の対象外**：給与収入2,000万円超は計算せず「対象外（本人が確定申告）」と表示する。
- **元Excelの踏襲**：シート名・欄番号（①〜㉞、Ⓐ〜Ⓘ）・セル番地・エラーメッセージの文言を変えない。追加した列（集計シートL列など）は `excel-spec.md` に記録する。

## 出典（令和8年分・2026年11月確認）

- 給与所得控除 No.1410：https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm
- 令和8年分 年末調整のしかた：https://www.nta.go.jp/publication/pamph/gensen/nencho2026/01.htm
- 所得税の確定申告：https://www.nta.go.jp/taxes/shiraberu/shinkoku/kakutei.htm
- 給与所得者で確定申告が必要な人 No.1900：https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1900.htm
