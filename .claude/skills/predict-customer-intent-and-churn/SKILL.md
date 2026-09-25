---
name: predict-customer-intent-and-churn
description: CDPの行動ログから顧客ごとの購入確率、LTV目安、離脱リスク、カテゴリ関心度（クロスセル候補）、最適配信チャネルを推定し、セグメントを付与する。配信やクーポン発行の前の対象者判定、休眠・離脱予兆の確認、次に勧める商品の選定に使う。
---

# ② 予測・セグメンテーション（predict_customer_intent_and_churn）

## 実行方法
```bash
python -m dm_agent call predict_customer_intent_and_churn \
  '{"customer_id":"C001","analysis_window_days":90,"prediction_targets":["purchase_propensity","churn_risk","category_affinity","optimal_channel"]}'
```
入力スキーマ: `schemas/predict_customer_intent_and_churn.json`

## prediction_targets と出力
| target | 出力 | 付与セグメント |
|---|---|---|
| purchase_propensity | `score_30d`（0〜1）、`ltv_180d_estimate`（目安） | `high_purchase_intent`（0.6以上） |
| churn_risk | `score`、`level`（high/medium/low）、30日活動トレンド | `churn_risk_high` |
| category_affinity | カテゴリ別スコア・根拠・推奨商品ID | `cross_sell_{category}`（high のみ） |
| optimal_channel | 配信同意済みチャネルのうちエンゲージメントが高い順 | - |

## モデルについて（必ず伝えること）
- 現在は `rule_based_baseline_v1`（説明可能なルール・スコア）です。スコアは**推定値（目安）**であり、実績や確約として報告しないでください。
- 関心度は「購入カテゴリの併売ルール（`config/catalog.json` の cross_sell_rules）」と「閲覧・カート・広告クリック」の重み付けで算出します。
- 本番では学習済みモデル（購買ラベル付きの履歴が十分に蓄積された後）へ差し替える前提です。

## 使い分けの目安
- 配信前: `category_affinity` + `optimal_channel`
- 休眠対策の対象抽出: `churn_risk`（`config/policy.json` の `churn_inactive_days` 基準）
- 広告の類似オーディエンス元リスト作成: `purchase_propensity`

## 注意
- この呼び出し自体は配信を行いません（プレイブックが予約した実行のみ自動配信につながります）。
- `optimal_channel.channel` が null の場合、同意済みチャネルがないため個別配信はできません。
