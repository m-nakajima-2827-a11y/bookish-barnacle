# グロウクロス Web集客 作業フォルダ

`.claude/skills/growcross-*` の各Skillが、ここに成果物を保存します。

| フォルダ・ファイル | 内容 | 作成するSkill |
|---|---|---|
| `keyword-map.md` | キーワードマップ | growcross-keyword-strategy |
| `content/` | 記事の構成案・下書き、月次の記事計画 | growcross-seo-content |
| `cvr/` | LP・CV導線の改善案 | growcross-lp-conversion |
| `ads/` | 広告の設計案・週次の運用記録 | growcross-ads-operation |
| `sns/` | SNSの投稿計画・投稿文 | growcross-sns-operation |
| `ma/` | MA設計書 | growcross-ma-nurturing |
| `reports/` | サイト診断、週次チェック、月次レポート、競合SEO分析表、重複判定表 | growcross-site-audit / growcross-reporting / growx-web-automation |
| `content/calendar.csv` | 6か月分のコンテンツカレンダー（Excelで開けます） | growx-web-automation |
| `runbooks/` | 定期実行の手順書（週次コンテンツ企画・月次SEO分析） | growx-web-automation |
| `data/` | GSC・GA4・ラッコキーワードのCSV置き場 | 担当者 |

会社・サービス情報（全Skill共通の前提）は `.claude/skills/growcross-web-marketing/references/profile.md` にあります。

## AI社員と定期実行
- AI社員: `.claude/agents/growx-ai-employee.md`（Skill: `growx-web-automation`）
- 毎週月曜 7:43（JST）: 週次コンテンツ企画 → `runbooks/weekly-content-planning.md`
- 毎月3日 8:47（JST）: 月次SEO分析 → `runbooks/monthly-seo-analysis.md`
- 成果物はブランチ `growx-ops` に蓄積されます。
- WordPressへの登録はChatGPT経由で行います（AI社員は入稿パッケージまで作成）。
