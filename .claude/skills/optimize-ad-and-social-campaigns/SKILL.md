---
name: optimize-ad-and-social-campaigns
description: Google広告・Meta広告・LINE広告・X広告に対し、購買済みユーザーの除外リスト同期、目標ROAS/CPAに基づく予算再配分、入札戦略の変更、低成果クリエイティブの停止を行う。無駄な広告費の削減、日次・週次の広告運用最適化、媒体へのセグメント連携に使う。
---

# ③ 広告・SNS最適化（optimize_ad_and_social_campaigns）

## 実行方法
```bash
python -m dm_agent call optimize_ad_and_social_campaigns '{"platform":"google_ads","action":"sync_audience_exclusion","target_segment_id":"purchased_outdoor_jacket"}'
python -m dm_agent call optimize_ad_and_social_campaigns '{"platform":"meta_ads","action":"update_budget","optimization_metrics":{"target_roas":2.0}}'
```
入力スキーマ: `schemas/optimize_ad_and_social_campaigns.json`

## action 別の動作とガードレール
| action | 必須入力 | ロジック | ガードレール |
|---|---|---|---|
| sync_audience_exclusion | target_segment_id | CDPセグメント所属者をSHA-256ハッシュ化して除外オーディエンスへ反映 | 生IDは送信しない |
| update_budget | target_roas または max_cpa | 直近7日ROAS/CPAと目標を比較し、**媒体内の総額を変えずに**キャンペーン間で再配分 | 1日の変更幅±20%。±10%超は承認待ち |
| adjust_bidding_strategy | target_roas または max_cpa | 目標ROAS／目標CPA入札へ切替 | 直近30日CV30件未満のキャンペーンはスキップ（学習不足） |
| pause_underperforming_creative | - | 表示1,000回以上かつCTRがキャンペーン平均の50%未満を停止 | 最後の稼働クリエイティブは停止しない |

`target_segment_id` を update_budget / adjust_bidding_strategy / pause_underperforming_creative に指定すると、そのセグメントを狙うキャンペーンに対象を絞ります。
閾値はすべて `config/policy.json` の `ads` で変更できます（初期値は仮の設定です）。

## 実行モード
- `execution_mode: "dry_run"`（既定）: 計画のみ返し、媒体へは反映しません（`status: planned`）。
- `execution_mode: "live"`: 媒体APIへ反映します。承認が必要な変更は `pending_approval` のまま保留されます。

## 報告ルール
- `planned` は「計画（未反映）」、`pending_approval` は「承認待ち」、`applied` のみ「反映済み」と書きます。
- 予算変更の根拠として `performance_7d`（費用・CV・売上・ROAS・CPA）を併記します。
- ROASの判断はアトリビューションレポート（⑤）と媒体報告値の両方を確認してから行います。
