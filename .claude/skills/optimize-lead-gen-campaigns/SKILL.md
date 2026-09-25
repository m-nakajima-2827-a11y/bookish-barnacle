---
name: optimize-lead-gen-campaigns
description: BtoBのリード獲得広告（Google・Yahoo!検索広告、Meta／Instagram広告、LinkedIn広告）を、リード単価ではなく商談化単価（Cost per SQL）で評価して最適化する。商談中・既存顧客・対象外リードの除外同期、予算の増減、入札戦略の変更、低成果クリエイティブの停止に使う。
---

# ④ リード獲得広告の最適化（optimize_lead_gen_campaigns）

## 実行方法
```bash
python -m dm_agent call optimize_lead_gen_campaigns '{"platform":"meta_ads","action":"update_budget","optimization_metrics":{"target_cost_per_sql":100000}}'
python -m dm_agent call optimize_lead_gen_campaigns '{"platform":"google_ads","action":"sync_audience_exclusion","target_segment_id":"open_opportunities"}'
```

## action 別の動作
| action | 必須入力 | 内容 | ガードレール |
|---|---|---|---|
| sync_audience_exclusion | target_segment_id | `customers`（既存顧客）/ `open_opportunities`（商談中）/ `disqualified`（対象外）/ `hot_leads` をハッシュ化IDで除外 | 生IDは送らない |
| update_budget | target_cost_per_sql（推奨）または target_cpl | 直近30日の費用と、CRMでSQLに到達したリード（UTMキャンペーンで紐付け）から商談化単価を算出して増減 | ±20%/日まで。±10%超は承認待ち。SQL3件未満は判断保留。SQL0件で目標の2倍以上を消化したら減額 |
| adjust_bidding_strategy | target_cpl または target_cost_per_sql | 目標CPA入札へ切替 | 直近30日の媒体CV30件未満はスキップ |
| pause_underperforming_creative | - | CTRがキャンペーン平均の50%未満（表示1,000回以上）を停止 | 最後の1本は停止しない |

## BtoBでの判断のポイント
- **CPLが安い＝良い広告ではありません。** 出力の `performance_30d` にある `crm_leads` / `sql` / `sql_rate` / `cost_per_sql` を必ず確認してください。
- SQLを最適化対象にした入札には、CRMのSQL到達を媒体へ送る（オフラインコンバージョン）設定が前提です。
- 広告のリンクは `build-utm-tracking-url` で作成したURLにしてください。UTMがないとCRMと紐付かず、商談化単価を計算できません。

## 報告ルール
`planned`＝計画（未反映）、`pending_approval`＝承認待ち、`applied`＝反映済み、と区別して書きます。
