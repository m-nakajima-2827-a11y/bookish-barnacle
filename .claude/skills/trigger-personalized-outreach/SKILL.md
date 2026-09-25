---
name: trigger-personalized-outreach
description: カゴ落ち、来店後フォロー、離脱防止、クロスセルの各シナリオで、アプリPush・LINE公式・メール・SMSから同意済みの最適チャネルを使い、個別化メッセージやクーポン（店舗・EC共通）を配信する。配信同意・頻度上限・配信停止時間帯・割引率上限を自動でチェックする。
---

# ④ パーソナライズド配信（trigger_personalized_outreach）

## 実行方法
```bash
python -m dm_agent call trigger_personalized_outreach '{
  "customer_id":"C001","selected_channel":"app_push",
  "campaign_scenario":"cross_sell_recommendation","offer_type":"store_coupon",
  "payload_details":{"product_ids":["SPR-010","SHO-100"],"discount_rate":0.1,"valid_days":14}}'
```
入力スキーマ: `schemas/trigger_personalized_outreach.json`

## 配信前の手順（必須）
1. `predict-customer-intent-and-churn` で `optimal_channel` と `category_affinity` を確認する
2. `selected_channel` は `optimal_channel.channel`（同意済み）から選ぶ
3. `product_ids` は `recommended_products` から選ぶ

## payload_details の主なキー
| キー | 内容 |
|---|---|
| product_ids | 推奨商品ID（abandoned_cart で省略時はカート残り商品を自動設定） |
| discount_rate | store_coupon の割引率（既定0.1、上限 `max_discount_rate`=0.2） |
| valid_days / expires_at | 有効期限（既定14日） |
| point_multiplier | point_multiplier のポイント倍率 |
| banner_url | ダイナミックバナーURL |

## ガードレール（`config/policy.json` の `outreach`）
| チェック | 既定値 | 結果 |
|---|---|---|
| チャネル別の配信同意 | 必須 | 未同意は `blocked`（個人情報保護法・特定電子メール法への配慮） |
| 頻度上限 | 7日で3通 | `blocked` |
| 同一シナリオのクールダウン | 7日 | `blocked` |
| 割引率上限 | 20% | `blocked`（景品表示法・利益率の観点で要事前合意） |
| 配信停止時間帯 | 21:00〜8:00（Push/SMS/LINE） | `scheduled`：翌8:00に自動送信 |

`blocked` の場合は回避せず、理由と必要な判断（同意取得、割引率の見直し等）を報告してください。

## 出力
- `status`: `sent` / `planned`（dry_run）/ `scheduled` / `blocked`
- `message`: 件名・本文・クーポンコード・利用可能チャネル（店舗POS/EC/アプリ）
- 本文テンプレートは下書きです。本番前にブランド・法務の確認を受けてください。
