---
name: generate-omnichannel-attribution-report
description: Web・アプリ・広告・SNS・メールと実店舗POS売上を統合し、ラストタッチ・ファーストタッチ・線形・減衰・位置ベース等のアトリビューションでチャネル別の売上貢献度と貢献ROASを算出し、改善提案付きレポート（Markdown/JSON）を出力する。週次・月次の効果検証、予算配分の根拠づくり、定例報告に使う。
---

# ⑤ アトリビューションレポート（generate_omnichannel_attribution_report）

## 実行方法
```bash
python -m dm_agent call generate_omnichannel_attribution_report \
  '{"period_start":"2026-09-01","period_end":"2026-09-30","attribution_model":"position_based","lookback_window_days":30}'
```
入力スキーマ: `schemas/generate_omnichannel_attribution_report.json`（本スキルは仕様書のレイヤー表をもとに新規設計）

## モデル
| attribution_model | 配分 |
|---|---|
| last_touch / first_touch | 最後／最初の接点に100% |
| linear | 均等 |
| time_decay | 半減期7日で直近を重視 |
| position_based | 最初40%・中間20%・最後40% |
| data_driven_mta / mmm | 外部分析基盤が必要。未接続時は position_based で代替し、注記に明記 |

- コンバージョン = `store_purchase`（店舗POS・EC）。`include_offline_sales: false` で店舗購買を除外します。
- ルックバック内にデジタル接点がない購買は「接点なし・直接」として計上します。
- 広告費は媒体別の日次実績（`ad_spend`）から集計し、貢献ROASと媒体報告ROASを並べて表示します。

## 改善提案のルール
- 紐付いたCVが30件未満 → 予算判断は保留し、会員ID連携率・計測基盤の確認を優先提案
- 貢献ROAS < 1.0 → 予算縮小またはターゲティング・クリエイティブ見直し（優先度: 高）
- 貢献ROAS ≥ 3.0 → 変更幅上限内での段階的増額を検討（優先度: 中）
- デジタル接点なしの購買が30%以上 → 店頭での会員ID提示率向上を提案

## 定例報告に使うときの構成
1. サマリー（CV・売上・広告費・紐付率）
2. チャネル別貢献表（レポートの表をそのまま使用）
3. 課題と原因（数値の根拠つき）
4. 改善提案（優先度・担当・実施時期）
5. 次回までのアクション

数値はレポート出力の値のみを使い、推測値を加える場合は「仮説」と明記してください。
