# 給与所得の計算（2026年（令和8年）分）

`skills/salary-income-calculator/SKILL.md` の仕様で作った、給与所得の自動計算Webアプリです。

## ファイル

| ファイル | 内容 |
|---|---|
| `index.html` | 画面（入力・計算結果・計算表・注意書き） |
| `calc.js` | 計算ロジック（整数演算。ブラウザとNode.jsの両方で動作） |
| `calc.test.js` | テスト（SKILL.md「7. テストケース」をすべて含む） |

## 使い方

`index.html` をブラウザで開きます（サーバー不要。`calc.js` を同じフォルダに置いてください）。

## テスト

```bash
node apps/salary-income-calculator/calc.test.js
```

## 注意

- 計算表は2026年（令和8年）分専用です。
- No.8（6,600,000円以上 8,499,999円以下）の `Ａ × 0.9` で出る1円未満の端数は切り捨てています（SKILL.md「8. 要確認事項」No.5）。
