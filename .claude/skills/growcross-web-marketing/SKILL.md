---
name: growcross-web-marketing
description: グロウクロス（https://www.grow-cross.com）のWeb集客を自動化する統括Skill。サイト診断、キーワード戦略、SEO記事制作、LP・CV導線改善、広告運用、SNS運用、MA（育成・引き渡し）、週次・月次レポートの各Skillを、どの順番・頻度で使うかを決めて実行する。「グロウクロスの集客を進めて」「今週のWeb集客タスクを回して」「集客の現状と次にやることを教えて」といった依頼で使う。
---

# グロウクロス Web集客 自動化（統括）

## 前提
- 対象サイト: https://www.grow-cross.com
- 会社・サービス情報は `references/profile.md` を正とします。**「要確認」の項目が残っている間は、その項目に依存する施策（広告の訴求文、記事の事例記述など）を確定させません。**
- 事実と仮説を分けて書きます。根拠のない数値・実績は作りません。試算は「想定」「目安」と明記します。

## 現状（確認済みの事実）
| 項目 | 内容 | 出典・取得日 |
|---|---|---|
| サービス | 営業コンサルティング、AIコンサルティング、営業の伴走支援 | ご担当者回答（2026-11-17） |
| 対象顧客 | 法人（中小企業中心）。製造業・サービス業・不動産・介護施設の運営事業者。全国 | ご担当者回答 |
| 優先する成果 | ①相談予約 ②問い合わせ | ご担当者回答 |
| SNS・広告 | Instagram・Facebookを運用中。広告は出稿なし | ご担当者回答 |
| Google検索での獲得キーワード | 100位以内のランクインが **0件**（www あり・なしとも） | ラッコキーワード 獲得キーワード調査（2026-11-17） |
| 候補キーワードの検索数 | `growcross/keyword-map.md`（初版）を参照 | ラッコキーワード（2026-11-17） |

## 重点方針（現状からの仮説）
1. **相談予約に直結する導線を最優先にする**: 全ページから相談予約へ1クリックで行けるようにし、予約完了をGA4のキーイベントで計測します（`growcross-lp-conversion`）。
2. **自然検索は「業種 × 課題」で始める**: 「営業コンサル」などの競争が激しい語より、4業種の具体的な課題の語から記事とサービスページを作ります（`growcross-keyword-strategy` / `growcross-seo-content`）。
3. **Instagram・Facebookをサイトと相談予約につなぐ**: 投稿から業種別のページへの導線をUTM付きで作り、どの投稿が相談につながったかを測ります（`growcross-sns-operation`）。
4. **広告は計測が整ってから判断する**: 相談予約の計測と受け皿のページが整った後に、少額の検索広告で検証するかを判断します（`growcross-ads-operation`）。

→ SEO流入がほぼない状態と考えられます。原因の切り分け（インデックスされていない／新しいサイト／狙うキーワードとページが合っていない など）が最初の課題です。どれに当たるかは **仮説** で、`growcross-site-audit` で確認します。

## 全体フロー
```
① サイト診断・プロファイル作成（growcross-site-audit）
        ↓ profile.md 完成・「要確認」の解消
② キーワード戦略（growcross-keyword-strategy）
        ↓ キーワードマップ
③ 集客施策を並行実行
   ├ SEO記事制作（growcross-seo-content）
   ├ LP・CV導線の改善（growcross-lp-conversion）
   ├ 広告運用（growcross-ads-operation）
   └ SNS運用（growcross-sns-operation）
        ↓ 問い合わせ・資料DL
④ 育成・営業引き渡し（growcross-ma-nurturing）
        ↓
⑤ 週次・月次レポートと改善（growcross-reporting）→ ②③へ戻す
```

## 実行の順番（初回）
| 週 | やること | Skill | 完了条件 |
|---|---|---|---|
| 1週目 | サイト診断、プロファイル作成、計測（GA4・サーチコンソール）の確認 | growcross-site-audit | `profile.md` の必須項目が埋まり、インデックス状況が分かっている |
| 1〜2週目 | キーワードマップ作成、記事テーマの優先順位付け | growcross-keyword-strategy | 優先キーワード20件以上と担当ページが決まっている |
| 1〜3週目 | 相談予約ツールの選定・設定、相談予約ページとGA4キーイベントの設定 | growcross-lp-conversion（`growcross/cvr/booking-tool-plan.md`） | テスト予約がGA4のキーイベントに記録される |
| 2週目 | 主要ページのタイトル・説明文・見出しの改善案、CV導線の改善案 | growcross-seo-content / growcross-lp-conversion | 改善案を承認者が確認済み |
| 3週目〜 | 記事制作（週1〜2本の想定）、Instagram・Facebook投稿 | 各Skill | 公開・配信のたびに計測用URL（UTM）を設定 |
| 計測が整った後 | 検索広告の開始判断（少額での検証） | growcross-ads-operation | 開始する／しないを判断済み |
| 毎週・毎月 | レポートと次のアクション | growcross-reporting | 次週・次月のタスクが決まっている |

## 定期実行（自動化）
| 頻度 | 依頼文の例 | 使うSkill |
|---|---|---|
| 毎週月曜 | 「グロウクロスの週次集客チェックをして、今週のタスクを出して」 | growcross-reporting（週次）→ 各Skill |
| 毎月1営業日 | 「グロウクロスの月次レポートを作成して」 | growcross-reporting（月次） |
| 毎月中旬 | 「来月のグロウクロスの記事とSNSの計画を作って」 | growcross-keyword-strategy → growcross-seo-content / growcross-sns-operation |

Claude Code の `/loop` や、クラウドの定期実行（ルーティン）にこの依頼文を設定すると、自動で回せます。

## 承認が必要な操作（自動で実行しない）
- サイトへの記事・ページの公開、既存ページの書き換え
- 広告の予算・入札の変更、新規キャンペーンの開始
- メール配信、SNS投稿の公開
- 外部サービス（広告媒体・MA・CMS）の設定変更

いずれも「案」または「下書き」までを作成し、承認者の確認を経てから実行します。

## 各Skillの出力の置き場所
| 出力 | ファイル |
|---|---|
| 会社・サービス情報 | `.claude/skills/growcross-web-marketing/references/profile.md` |
| キーワードマップ | `growcross/keyword-map.md` |
| 記事の構成案・下書き | `growcross/content/YYYY-MM-DD_<slug>.md` |
| LP・CV改善案 | `growcross/cvr/` |
| 広告運用の計画・記録 | `growcross/ads/` |
| SNS投稿計画 | `growcross/sns/` |
| レポート | `growcross/reports/` |
