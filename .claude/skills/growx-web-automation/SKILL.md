---
name: growx-web-automation
description: グロウクロス（GrowX / https://www.grow-cross.com）専用のWEB集客自動化Skill。WEBサイト・既存記事の分析 → 競合SEO・キーワード調査 → 検索需要・重複・優先順位の判定 → コンテンツカレンダー（6か月）→ 記事・画像・フロー図の制作 → WordPress公開準備（入稿パッケージ）→ 効果測定・改善提案までを一連の業務として標準化する。「営業改善・WEB改善・AI活用」の3領域で、無料診断・資料請求・お問い合わせの獲得につなげる。毎週のコンテンツ企画、毎月のSEO分析、記事制作の依頼で使う。
---

# GrowX WEB集客自動化 Skill

## 目的と前提
- 3つの集客領域: **営業改善／WEB改善／AI活用**。すべての記事・施策は、いずれかの領域と CV（無料診断・資料請求・お問い合わせ）に紐づけます。
- 会社・サービス情報は `.claude/skills/growcross-web-marketing/references/profile.md` を正とします。「要確認」の項目に依存する記述（事例・料金・実績）は確定させません。
- 事実と仮説を分けます。根拠のない数値・実績は作りません。試算は「想定」「目安」「仮説」と明記し、取得値には出典と取得日を付けます。
- **WordPressへの記事登録は ChatGPT 経由で行います。** このSkill（Claude）は「入稿パッケージ」の作成までを担当し、WordPress への登録・公開・既存記事の書き換えは行いません（WordPress.com コネクタがあっても使いません）。

## 入力データ（置き場所）
| データ | 置き場所 | 取得方法 |
|---|---|---|
| 獲得KW・競合・検索数・見出し・共起語・質問 | （MCPで直接取得） | ラッコキーワードMCP |
| ラッコキーワードのCSV（手動エクスポート分） | `growcross/data/rakko/` | 担当者がアップロード |
| サーチコンソール（クエリ・ページ別の表示回数・クリック・順位） | `growcross/data/gsc/YYYY-MM_*.csv` | 担当者が管理画面からエクスポート |
| GA4（ページ別セッション・キーイベント） | `growcross/data/ga4/YYYY-MM_*.csv` | 担当者が管理画面からエクスポート |
| 既存記事一覧 | `growcross/content/existing-articles.csv` | サイトの読み取り（sitemap.xml）で作成・更新 |

GSC・GA4のファイルがない場合は、その項目を「データ未取得」とし、数値を推測で埋めません。

## 実行ワークフロー（9ステップ）
| # | ステップ | やること | 使う既存Skill／ツール | 成果物 |
|---|---|---|---|---|
| 0 | 入力確認 | profile.md の「要確認」、data/ の新着ファイル、前回の成果物を確認 | - | 実行ログ冒頭の「入力状況」 |
| 1 | WEBサイト・既存記事の分析 | sitemap.xml・主要ページを読み、サイト構造・既存記事・CTAを整理 | growcross-site-audit | `existing-articles.csv` 更新 |
| 2 | 競合SEO・キーワード調査 | 競合ドメインの獲得KW・集客ページ、関連語・質問を取得。CSVがあれば併用 | growcross-keyword-strategy／`competitive` `influx-keywords` `influx-pages` `related-keywords` `question-search` | 競合SEO分析表 |
| 3 | 検索需要・重複・優先順位の判定 | 検索数・難易度（`search-volume-history`）、GSC、既存記事と照合し「新規／リライト／統合／見送り」を判定 | growcross-keyword-strategy | 重複判定表、`keyword-map.md` 更新 |
| 4 | コンテンツカレンダー作成 | 6か月分の企画を `content/calendar.csv`（Excelで開ける）に登録・更新 | growcross-seo-content | コンテンツカレンダー |
| 5 | 記事・画像・フロー図の制作 | 構成案 → 承認 → 本文、アイキャッチ・図解の指示書、CTA | growcross-seo-content | SEO記事制作パッケージ |
| 6 | WordPress公開準備 | ChatGPTでの登録用に、タイトル・スラッグ・説明文・カテゴリ・タグ・本文HTML・画像alt・公開前チェックをまとめる | - | 入稿パッケージ（`status=承認待ち`） |
| 7 | 効果測定 | 公開済み記事の順位（`search-rank-history`）、GSC・GA4の流入・CV | growcross-reporting | 月次改善レポート |
| 8 | 継続改善 | 11〜20位・高表示低CTR記事のリライト、カレンダーの入れ替え提案 | growcross-reporting → 4へ戻る | 改善提案・次月カレンダー |

### ステップ3の判定ルール
| 条件 | 判定 |
|---|---|
| 同じ検索意図の既存記事があり、順位が11位以下または未ランク | リライト |
| 同じ検索意図の既存記事が2本以上 | 統合（1本に寄せ、他は301リダイレクト案） |
| 既存記事なし、3領域・CVと関連が強い | 新規 |
| 3領域と関連が弱い、または難易度が高く当面勝てない | 見送り（理由を記録） |

優先度スコア（目安）＝ 事業関連度(1-3) × 購買への近さ(1-3) × 難易度の低さ(1-3)。同点なら CV導線（無料診断・資料請求）に直結する方を優先します。

## 成果物のフォーマット
各成果物の列定義は `references/templates.md` を参照します。

| 成果物 | ファイル |
|---|---|
| 競合SEO分析表 | `growcross/reports/competitor-seo_YYYY-MM.md` |
| 重複判定表 | `growcross/reports/duplicate-check_YYYY-MM.md` |
| コンテンツカレンダー | `growcross/content/calendar.csv`（正）／週次の企画: `growcross/content/weekly-plan_YYYY-MM-DD.md` |
| SEO記事制作パッケージ | `growcross/content/YYYY-MM-DD_<slug>.md` |
| 月次改善レポート | `growcross/reports/monthly-seo_YYYY-MM.md` |

## 定期実行
| 頻度 | 内容 | 手順書 |
|---|---|---|
| 毎週月曜 7:43（JST） | 週次コンテンツ企画（ステップ0・3・4・5の構成案まで） | `growcross/runbooks/weekly-content-planning.md` |
| 毎月3日 8:47（JST） | 月次SEO分析（ステップ1・2・3・7・8） | `growcross/runbooks/monthly-seo-analysis.md` |

※ 月次を3日にしているのは、サーチコンソールのデータ反映に2日程度の遅れがあるためです。

## 承認が必要な操作（自動では実行しない）
- WordPress への登録・公開・既存記事の変更（ChatGPT経由で担当者が実施）
- 構成案から本文執筆への移行（構成案の承認後）
- 301リダイレクト・記事の統合・削除
- 広告・SNS・メール配信の実行

## 守ること
- ラッコキーワードはクレジットを消費します。同じ条件の再取得はせず、取得結果は `growcross/data/rakko/` に保存して再利用します。
- 他社記事の文章を流用・言い換えしません。競合の社名を否定的に扱いません。
- 事例・数値は profile.md で掲載許可されたもの、または出典付きの公開データのみ使います。
