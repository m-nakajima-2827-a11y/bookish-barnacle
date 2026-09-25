---
name: btob-lead-to-deal-workflow
description: BtoBの自動化ワークフロー（Instagram・広告・検索からの資料DL→自動スコアリング→MQLは業界別育成／ホットリードは30分以内の営業引き渡し→商談化で広告除外→失注は予算編成時期に再アプローチ）を実行・デモ・点検する。リード獲得から商談化までの一連の流れを動かしたい、自動化ルールを確認・変更したいときに使う。
---

# BtoB リード獲得→商談化 ワークフロー

## 流れ
| # | きっかけ | 実行されるスキル | 内容 |
|---|---|---|---|
| 1 | 資料DL・セミナー申込・問い合わせ／セミナー参加・料金ページ・事例閲覧 | score_and_qualify_leads | 即時にスコアを再計算 |
| 2 | MQLに到達 | trigger_nurture_action（enroll_nurture_track） | 業界別の育成メール（営業時間内に配信） |
| 3 | ホットリードに到達 | trigger_nurture_action（sales_handoff） | CRMにタスク作成。初回接触期限は営業時間内30分 |
| 4 | 引き渡し・商談設定・受注 | optimize_lead_gen_campaigns（sync_audience_exclusion） | 商談中・既存顧客を広告配信から除外 |
| 5 | 失注（timing / budget） | trigger_nurture_action（schedule_recontact） | 予算編成時期（仮定）に再アプローチのタスク |

ルールは `src/dm_agent/workflow.py`、しきい値は `config/policy.json` と `config/clients/<client>.json` にあります。

## デモ
```bash
python -m dm_agent demo            # モック接続に反映（live）して全ステップを表示
python -m dm_agent demo --dry-run  # 計画のみ
```
サンプル: `examples/scenario_btob_sales_consulting.json`（架空の営業コンサル会社。製造業・IT企業がターゲット）。レポート・投稿カレンダー・監査ログは `reports/` に保存されます。

## 点検観点
- 営業時間外のDLで、初回メールが翌営業日9:00に予約されているか
- ホットリードのCRMタスクの `due_at` が、営業時間内で30分以内になっているか
- SQL以降のリードに育成メールが送られていないか（`skipped` になっているか）
- 監査ログ（`reports/demo_audit_log.jsonl`）の `origin`（playbook / scheduler / nurture_track / llm / direct）

## クライアントの追加
`config/clients/sample_sales_consulting.json` を複製して、ICP（業界・規模・役職の配点）、育成シナリオ、コンテンツ一覧、投稿テーマ、UTM命名辞書を書き換えます。`--client <ファイル名>` で切り替えます。
