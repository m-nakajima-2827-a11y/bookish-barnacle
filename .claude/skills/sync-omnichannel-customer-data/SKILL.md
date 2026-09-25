---
name: sync-omnichannel-customer-data
description: 実店舗POS・EC/Web・アプリ・SNS・メールの接点データを共通顧客IDに統合し、CDPの顧客プロファイル（購買カテゴリ、カゴ落ち、同意状態、セグメント）を更新する。POSレジでの会員スキャン、EC行動ログ、アプリイベントを取り込むとき、顧客の最新状態を確認したいときに使う。
---

# ① オムニチャネルデータ統合（sync_omnichannel_customer_data）

## 目的
オンライン・オフラインの接点を同一顧客IDに紐付け、後続スキル（予測・広告抑制・配信）の判断材料を最新化します。

## 実行方法
```bash
python -m dm_agent call sync_omnichannel_customer_data '<JSON>'   # または .json ファイルパス
```
入力スキーマ: `schemas/sync_omnichannel_customer_data.json`

```json
{
  "customer_id": "C001",
  "touchpoints": [
    {"channel": "physical_store_pos", "timestamp": "2026-09-20T11:00:00+09:00",
     "event_type": "store_purchase",
     "payload": {"store_code": "S001", "amount": 29800, "skus": ["JKT-001"]}}
  ]
}
```

## payload の取り決め
| event_type | 推奨キー |
|---|---|
| store_purchase | `amount`（税込円）, `skus`（配列）, `store_code` または `order_id` |
| cart_add | `sku` |
| page_view | `url`, `sku` または `category` |
| ad_click | `platform`（google_ads / meta_ads / line_ads / x_ads）, `campaign_id` |
| 全イベント共通 | `consent`: `{"app_push": true, "email": false, ...}`（同意の取得・撤回時のみ） |

- `store_purchase` は channel が `physical_store_pos` なら店舗購買、`web` / `mobile_app` ならEC購買として扱います。
- SKU→カテゴリの対応は `config/catalog.json` を参照します。未登録SKUはカテゴリ判定されません。

## 処理内容
1. 同一イベント（顧客ID・チャネル・時刻・種別・payload が一致）は重複として除外（冪等）
2. 接点回数、購買回数・金額、購入カテゴリ、カゴ落ち（未購入の cart_add）、同意状態を更新
3. 購入カテゴリごとに `purchased_{category}` セグメントを付与し、`category_purchased` イベントを発行
   → 自動化プレイブックが広告除外と3日後の予測を起動します（`omnichannel-store-web-workflow` 参照）

## 出力の読み方
- `accepted_events` / `duplicate_events_skipped`: 取り込み件数と重複除外件数
- `derived_signals`: 購買カテゴリなど、後続処理のトリガーになった事実
- `profile`: 更新後プロファイルの要約

## 注意
- 顧客IDはハッシュ化済み会員IDを使い、氏名・電話番号・メールアドレスを payload に入れないでください。
- 同意情報（consent）が取り込まれていない顧客には、配信スキルがブロックをかけます。
