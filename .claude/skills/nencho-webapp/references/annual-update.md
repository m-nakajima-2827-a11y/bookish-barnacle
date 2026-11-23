# 年度更新・カスタマイズ手順

## 1. 翌年分（令和9年分など）への更新
1. 国税庁の資料を確認する（推測で数値を変えない）。
   - 「令和◯年分 年末調整のしかた」：https://www.nta.go.jp/publication/pamph/gensen/ の該当年度ページ
     - 「Ⅰ 昨年と比べて変わった点」、巻末の「速算表・配偶者控除額一覧・基礎控除額の表・特定親族特別控除額の表・扶養控除額等の表」、「保険料控除申告書の受理と内容の確認」
   - 給与所得控除 No.1410（年分ごとの表と特例）
   - 国税庁の「年末調整計算シート（令和◯年用）」が公開されていれば、その計算シートの関数（M17・AC17・T30 など）と入力規則
2. `assets/app/js/engine.js` の `TABLES` を更新：`year`、`label`、`salaryIncome`、`basic`、`spouse*`、`tokuteiShinzoku`、所得要件、`deductions`、`life`、`taxRates` など。
3. `assets/app/js/workbook.js` の「控除テーブル」シートの値、計算シート M17 の式、年号・タイトル文字列を更新。
4. 画面の年号（`index.html` の badge、`app.js` の「令和8年」表記、STORE_KEY）を更新。STORE_KEY を変えると前年データと分けて保存できる。
5. `references/tax-rules-r8.md` を新年度版として複製・更新し、出典の確認日を書く。
6. `scripts/test_engine.js` の境界値を新しい表に合わせて書き換え、3種類の検証（SKILL.md「4. 変更したら必ず検証する」）を通す。

※ 令和8・9年分は基礎控除の特例加算・給与所得控除74万円が同じ。令和10年分以後は基礎控除が「132万円以下99万円／それ以外62万円」となる予定（令和8年分 年末調整のしかた p.3）。

## 2. よくあるカスタマイズ
| 要望 | 変更箇所 |
|---|---|
| 会社独自の給与明細を読ませたい | `payslip.js` の `LABELS`／`EXCLUDE` |
| 入力項目を増やしたい | `engine.js` の `blankEmployee` に項目追加 → `app.js` の画面に `data-bind` で入力欄 → 計算に使うなら `calculate` |
| 計算結果の表示を増やしたい | `calculate` の戻り値に追加 → 画面に `data-out="パス"` |
| Excelにシートを足したい | `workbook.js`（シート名を `SH` に追加し、`ws[...]` に書く） |
| 社内サーバーで複数人共有したい | 現状は端末ごとのlocalStorage保存。共有するならサーバーAPI＋認証＋暗号化を別途設計（個人情報のため、担当者に要件を確認） |
| 源泉徴収票を出したい | 計算結果（⑦・⑧・㉖・各控除）から作成可能。法定調書の手引の様式に合わせて新しい画面・シートを追加 |

## 3. 配布
- `node scripts/build_single_html.js` で `dist/nencho-app.html`（CSS・JSを1ファイルに埋め込み）を作り、配布する。
- pdf.js・ExcelJS は cdnjs から読み込む。社内ネットワークで外部CDNが使えない場合は、両ライブラリを同じフォルダに置き `index.html` の `src` をローカルパスに変える。
