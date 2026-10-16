# BtoB デジタルマーケティング AIエージェント

BtoB（企業間取引）向けに、Webサイト・LP・Instagram・メール・ウェビナー・広告のデータを使い、**見込み顧客の獲得 → 育成 → 見極め → 営業への引き渡し → 商談化**までを実行・改善するAIエージェントです。

BtoBは検討期間が長く、複数人が意思決定に関わります。そのため、このエージェントは次の方針で判断します。

- リード数やリード単価（CPL）ではなく、**商談化（SQL・商談金額）** で評価します。
- 同一企業の複数担当者の動きも評価します。
- ホットリードは**30分以内に営業へ引き渡します**。
- 失注したリードには、**予算編成時期に合わせて再アプローチ**します。

MA（マーケティングオートメーション）は外部ツールを使わず、**SATORIの機能構成に準拠した自社開発のMA**をSkillとして内蔵しています。SATORI機能との対応は [`docs/ma_spec_satori_based.md`](docs/ma_spec_satori_based.md) を参照してください。

| 収録物 | 場所 |
|---|---|
| ツール定義（JSON Schema・18本＝BtoB 7本＋MA 11本） | `schemas/`（OpenAI / LangChain 形式と Claude API 形式は `schemas/export/`） |
| Claude Code 用エージェントと Skill | `.claude/agents/btob-marketing-agent.md`, `.claude/skills/`（14本） |
| 実行基盤（Python） | `src/dm_agent/`（MAは `src/dm_agent/ma/` と `src/dm_agent/skills/ma.py`） |
| MA機能仕様書 | `docs/ma_spec_satori_based.md` |
| クライアント別設定 | `config/clients/<client_id>.json` |
| ガードレール | `config/policy.json` |

---

## 1. 3つの基本ステップとスキルの対応

| ステップ | 目的 | スキル |
|---|---|---|
| リード獲得（リードジェネレーション） | SEO・Web広告・Instagram・資料DL・ウェビナーで企業と担当者の情報を集める | `optimize_lead_gen_campaigns`, `build_utm_tracking_url`, `plan_social_content_calendar` |
| リード育成（リードナーチャリング） | 業界別のメール・セミナーで検討度を高める | `trigger_nurture_action`（育成シナリオ・メール・セミナー招待・資料推奨） |
| リードの見極め（リードクオリフィケーション） | 行動データからホットリードを見極め、営業へ引き渡す | `score_and_qualify_leads`, `trigger_nurture_action`（sales_handoff） |
| 共通（データ・分析） | 行動データの統合と、流入からファネルまでの分析 | `sync_lead_activity`, `analyze_marketing_funnel` |

### 自社開発MA（SATORIの機能構成に準拠）

| 機能 | ツール | 主な内容 |
|---|---|---|
| 計測（匿名客・実名客） | `ma_track_activity` | Webアクセス・UTM、メール開封/クリック/配信停止、ポップアップ、プッシュを記録し、スコア・セグメント・シナリオに反映 |
| カスタマー管理 | `ma_manage_customer` | 参照・検索・属性・タグ・配信停止・同意記録（連絡先は常にマスク） |
| フォーム | `ma_manage_form` | 名寄せ・実名化（匿名時代の行動を引き継ぐ）、同意記録、自動返信、Slack等への通知、リード登録 |
| LP | `ma_create_landing_page` | フォーム・計測タグ入りのキャンペーンLP（HTML） |
| セグメント | `ma_manage_segment` | 閲覧・UTM・メール反応・フォーム・タグ・スコア・属性・匿名/実名などの条件で自動抽出 |
| スコア定義 | `ma_configure_scoring` | 共通設定（Webアクセス+5・クリック+10・開封+1・配信停止−30）と個別設定（URL・パラメータ・フォーム・タグ・セグメント） |
| シナリオ | `ma_manage_scenario` | トリガー → ステップメール・タグ・社内通知（Webhook・CRMタスク）、離脱条件 |
| メール | `ma_send_email` | 個別・一斉・予約・テスト、差し込み、計測、配信停止リンク |
| ポップアップ | `ma_manage_popup` | 表示条件（セグメント・URL・匿名/実名・頻度・秒数・期間） |
| Webプッシュ | `ma_send_web_push` | 許諾者（匿名客を含む）へのセグメント配信 |
| レポート | `ma_get_report` | 実名化率・スコア分布、メール・ポップアップ・フォーム・プッシュ・シナリオの実績 |

```mermaid
flowchart LR
  IG[Instagram<br/>投稿・ストーリーズ] -->|UTM付きプロフィールリンク| LP
  AD[検索・SNS広告] -->|UTM| LP
  SEO[検索（SEO）] --> WEB[Webサイト]
  LP[業界別キャンペーンLP] -->|資料DL・セミナー申込| S1[① sync_lead_activity]
  WEB --> S1
  S1 --> S2[② score_and_qualify_leads<br/>フィット×エンゲージメント]
  S2 -- MQL --> N[③ 業界別育成メール<br/>資料→事例→セミナー→診断]
  N -.行動.-> S1
  S2 -- ホットリード --> H[③ 営業へ引き渡し<br/>CRMタスク・30分以内]
  H --> OPP[商談・受注]
  OPP --> X[④ 広告除外<br/>商談中・既存顧客]
  OPP -- 失注（時期・予算） --> R[③ 予算編成時期に再アプローチ]
  GA[GA4 / サーチコンソール / CRM] --> F[⑦ analyze_marketing_funnel<br/>改善提案]
```

## 2. 想定ケースへの適用（サンプル設定）

`config/clients/sample_sales_consulting.json` には、今回の相談内容をもとにした設定を入れています。

| 項目 | 設定内容 |
|---|---|
| 事業 | 中小企業の営業組織を仕組み化する営業コンサル（架空） |
| ターゲット | 中小のIT企業、製造業の営業組織（クライアントによって異なるため、業界別に配点・シナリオ・投稿テーマを分けています） |
| Instagram | これから立ち上げ。プロフィールは業界共通の課題でまとめ、投稿テーマは業界別に分けます。ハイライトは「IT企業の実績」「製造業の実績」 |
| Webサイト | 既存サイトあり。GA4・UTM・サーチコンソールで流入を分析します |
| LP | キャンペーンごとに作成します。LPごとのCVRと商談化はファネル分析（landing_page 軸）で比較します |

### 推奨の進め方（目安）

| 時期 | 実施内容 | 担当（想定） | 使うスキル | KPI |
|---|---|---|---|---|
| 1〜2週目 | GA4で資料DL完了をキーイベントに設定、サーチコンソールを連携、UTM命名ルールを確定 | Web担当 | `build_utm_tracking_url` | 計測漏れ（UTMなしのLP流入）ゼロ |
| 2週目 | Instagramのプロフィール設計、業界別のプロフィールリンク（UTM付き）の作成 | SNS担当 | `plan_social_content_calendar`（account_status: new） | プロフィール完成 |
| 3週目〜 | 週2〜3回の投稿（月: 図解カルーセル、金: 事例。水: 中の人リールは任意）、セミナー告知ストーリーズ | SNS担当 | `plan_social_content_calendar` | 保存数、プロフィールアクセス率 |
| 常時 | 資料DL後の自動スコアリング、業界別育成、ホットリードの30分以内の引き渡し | MA担当・インサイドセールス | ②③ と自動化ルール | 初回接触までの時間、SQL率 |
| 毎月 | ファネル分析・改善提案、広告の予算調整、スコア配点の見直し | マーケ責任者 | ⑦④② | 資料DL数、SQL数、商談金額、商談化単価 |

## 3. クイックスタート

```bash
pip install -e ".[dev,llm]"

python -m dm_agent demo              # BtoBシナリオを実行（メール・CRM・広告はモック接続に反映）
python -m dm_agent demo --dry-run    # 反映せず計画のみ
python -m pytest                     # テスト（44件）
```

`demo` では、サンプルデータ（架空）を使って次の流れを再現します。

0. Instagramプロフィール用のUTM付きURLと、MAでキャンペーンLP（フォーム・計測タグ入り）を作成します。
1. 9/2、匿名の訪問者がInstagram経由でLPと事例を閲覧します。MAが匿名のまま行動とスコアを記録します。
2. 9/7 20:25、LPを再訪してセグメント「匿名でLPを2回以上閲覧」に該当し、資料DLポップアップが表示されます。
3. 20:30、ポップアップのフォームから資料をDLします。実名化され（匿名時代の行動5件と流入元Instagramを引き継ぎ）、資料が自動返信で届き、Slackに通知されます。リード登録 → MQL → MAの製造業向け育成シナリオへと進みます。同じ会社ドメインの役員の閲覧も加味されます。
4. 別の匿名訪問者がWebプッシュを許諾し、セミナー告知を配信します。
5. 9/10、セミナー参加と料金ページ閲覧でホットリードになり、CRMに初回接触タスク（30分後期限）が作られます。育成シナリオはここで自動で離脱します。
6. 9/11、MAから「製造業・配信可」セグメントへセミナー案内を配信します（テスト確認 → 配信）。
7. 商談設定で広告から除外し、別リードの失注（時期）では2027年1月4日（予算編成時期と仮定）に再アプローチのタスクを作ります。
8. MAレポート（概要・メール・シナリオ・ポップアップ）とファネル分析を出力し、LPのHTMLを `reports/` に保存します。

### スキルを個別に実行する（MAの例を含む）

```bash
python -m dm_agent call build_utm_tracking_url '{"base_url":"https://example.com/lp/it-toss-criteria","utm_source":"instagram","utm_medium":"social","utm_campaign":"it_paper","placement":"instagram_story","target_industry":"it_saas"}'
python -m dm_agent call analyze_marketing_funnel '{"period_start":"2026-09-01","period_end":"2026-09-30","group_by":"landing_page"}' --client sample_sales_consulting
python -m dm_agent call ma_manage_segment '{"action":"preview","conditions":{"all":[{"type":"page_view","url_contains":"/price","within_days":30},{"type":"identified","value":true}]}}'
python -m dm_agent call ma_get_report '{"report_type":"overview"}'
```
状態は `state/<client_id>.json`（リード）と `state/<client_id>_ma.json`（MA）に保存されます。

## 4. エージェントとして使う

### A. Claude Code
このリポジトリを開くと、`btob-marketing-agent` と14の Skill（MA用6つを含む）が読み込まれます。
例:「btob-marketing-agent で、先月のファネルを分析して、商談化しない原因と改善策をまとめて」

### B. Claude API（自律実行ループ）
```bash
export ANTHROPIC_API_KEY=...
python -m dm_agent agent "Instagram経由のリードが商談化しているか分析し、来月の投稿方針を提案して" --scenario
```
- モデルの既定は `claude-opus-5` です（`--model` で変更可能）。adaptive thinking を有効にしています。
- 拒否応答時に代替モデルへ切り替えるサーバー側フォールバック（`fallbacks="default"`）を有効にしています。
- Claude が選んだツール呼び出しにも、スキーマ検証・ガードレール・監査ログが同じように適用されます。

### C. OpenAI Functions / LangChain など
`schemas/export/tools.openai.json` を読み込み、ツール呼び出しを `AgentRuntime(client_id=...).execute(name, args)` に渡してください。

## 5. ガードレール（`config/policy.json`。数値は初期値の仮置きです）

| 区分 | 項目 | 初期値 | 動作 |
|---|---|---|---|
| 全体 | execution_mode | `dry_run` | `live` のときだけメール・CRM・広告へ反映 |
| 全体 | 営業時間 | 平日9:00〜18:00（年末年始休業） | メール配信・初回接触期限の計算に使用。祝日は未対応 |
| メール | 配信同意・配信停止 | 必須 | `blocked`（特定電子メール法。配信停止リンク・送信者情報は自動付与）。フォームへの自動返信（請求資料の送付）は対象外（要法務確認） |
| メール | 頻度上限／同一資料の再送 | 7日で2通／30日 | `blocked` |
| Webプッシュ | 頻度上限・配信時間 | 7日3回・営業時間内 | 超過分は除外、時間外は翌営業日に予約 |
| 個人情報 | 連絡先の扱い | MA内のみ保持 | 出力・監査ログ・Webhookではマスク |
| 営業連携 | 引き渡し条件 | ホットリードのみ | それ以外は `blocked` |
| 営業連携 | 初回接触期限 | 営業時間内30分 | CRMタスクの期限に設定し、分析で達成状況を確認 |
| 広告 | 予算変更幅／承認 | ±20%／±10%超は承認待ち | 補正・`pending_approval` |
| 広告 | 予算判断に必要なSQL | 3件 | 未満は判断保留（SQL0件で目標の2倍以上を消化した場合は減額） |
| 広告 | 入札変更に必要なCV | 30件/30日 | 未満はスキップ |

スコア配点・MQL／ホットリードのしきい値は、クライアント設定（`icp` / `scoring`）にあります。**初期値は仮説のため、SQL・受注の実績を見て営業部門と合意のうえ調整してください。**

## 6. 本番導入に向けて（未実装・要対応）

| 項目 | 現状 | 本番での対応 |
|---|---|---|
| MA（自社開発） | 機能ロジックは実装済み。保存はJSONファイル | 計測タグ（tag.js）とトラッキング用エンドポイント、データベース移行、管理画面（詳細は `docs/ma_spec_satori_based.md`） |
| メール配信基盤 | `MockEmail` | Amazon SES / SendGrid 等。SPF・DKIM・DMARC、バウンス処理 |
| Webプッシュ | `MockWebPush` | Service Worker と VAPID 鍵による送信 |
| CRM（営業タスク・商談） | `MockCRM` | Salesforce / HubSpot CRM 等に接続。商談・受注・失注を `sync_lead_activity` に連携 |
| 広告媒体 | `MockAdPlatform` | Google広告 / Yahoo!広告 / Meta Marketing / LinkedIn Marketing API。SQLのオフラインコンバージョン送信も設定 |
| GA4 | サンプルJSON | GA4 Data API または BigQuery エクスポートから `ga4_sessions` を取得 |
| サーチコンソール | サンプルJSON | Search Console API から `gsc_queries` を取得 |
| Instagram | 投稿計画のみ | 投稿・インサイト取得は Instagram Graph API（ビジネスアカウント）で連携可能 |
| 祝日 | 年末年始のみ | 祝日カレンダーを `business_hours` に追加 |
| 予約ジョブ・承認 | プロセス内メモリ | ジョブキューと承認UI（Slack 等）へ移行 |

> `examples/` のデータ（企業・数値）はすべて動作確認用の架空の値で、実績ではありません。

## 7. 前バージョン（BtoC・オムニチャネル版）からの変更

店舗POS・クーポン配信を中心としたBtoC版を、BtoBのリード獲得から商談化までのファネル向けに作り替えました。前バージョンは Git の履歴から参照できます。
