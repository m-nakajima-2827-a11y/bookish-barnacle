---
name: omnichannel-store-web-workflow
description: 実店舗×Web連動の自動化ワークフロー（店舗購買検知→広告の購買者除外→3日後の関心予測→クロスセルPush配信）を実行・シミュレーション・点検する。オムニチャネル施策の一連の流れを動かしたい、デモしたい、自動化ルールを確認・変更したいときに使う。
---

# 実店舗 × Web 連動ワークフロー

## 流れ
| # | タイミング | 実行スキル | 内容 |
|---|---|---|---|
| 1 | レジで会員バーコードをスキャン | sync_omnichannel_customer_data | 購入カテゴリ（例: outdoor_jacket）をプロファイルに記録 |
| 2 | 直後（自動） | optimize_ad_and_social_campaigns ×媒体 | `purchased_{category}` を Google / Meta のリマーケティングから除外 |
| 3 | 3日後（予約ジョブ） | predict_customer_intent_and_churn | 併売カテゴリ（防水スプレー・登山靴）の関心度を判定 |
| 4 | 関心度 high のとき（自動） | trigger_personalized_outreach | 最適チャネルで「店舗・EC共通の関連ギア10%OFFクーポン」を配信 |

自動化ルールは `src/dm_agent/workflow.py`、パラメータは `config/policy.json` の `workflow` にあります。

| 設定 | 既定 |
|---|---|
| post_purchase_followup_days | 3 |
| exclusion_platforms | google_ads, meta_ads |
| cross_sell_offer_type | store_coupon |
| cross_sell_discount_rate | 0.1 |

## 動かし方
```bash
python -m dm_agent demo            # モック媒体に反映（live）して全ステップを表示
python -m dm_agent demo --dry-run  # 媒体・配信へは反映せず計画のみ
```
サンプルデータ: `examples/scenario_store_web.json`（架空データ）。出力は `reports/` に保存されます。

## 点検観点
- ステップ2で両媒体のリマーケティングに除外が付いたか（`excluded_on`）
- ステップ3の推奨カテゴリが購入済みカテゴリを含まないか
- ステップ4が同意・頻度・時間帯・割引率のガードレールを通過したか（`blocked` / `scheduled` の理由）
- 監査ログ `reports/demo_audit_log.jsonl` に全呼び出しが `origin`（playbook / scheduler / llm / direct）つきで残っているか

## 変更時の注意
- 手動・LLMからの予測呼び出しでは自動配信は発火しません（予約ジョブ経由のみ）。この仕様を変える場合は二重配信のリスクを確認してください。
- ルールを変更したら `python -m pytest` を実行してください。
