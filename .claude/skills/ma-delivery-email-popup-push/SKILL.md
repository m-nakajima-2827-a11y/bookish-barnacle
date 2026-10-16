---
name: ma-delivery-email-popup-push
description: 自社開発MA（SATORIの機能構成に準拠）の配信機能。実名客・セグメントへのメール配信（メルマガ・セミナー案内、予約・テスト、差し込み、開封・クリック計測、配信停止リンク）、サイト訪問者へのポップアップ（表示条件・頻度）、プッシュ許諾者（匿名客を含む）へのWebプッシュ通知に使う。
---

# MA: 配信（ma_send_email / ma_manage_popup / ma_send_web_push）

## メール（ma_send_email）
```bash
python -m dm_agent call ma_send_email '{"segment_id":"SEG-MFG-OPTIN","subject":"【10/1開催】BtoB営業組織の立ち上げ方",
  "body":"{{company_name}} ご担当者様\nセミナーのご案内です。","asset_id":"WB-GEN-01","campaign":"webinar_oct","test_only":true}'
```
- 送信前に必ず `test_only: true` で対象人数・配信可能数を確認します。
- 自動で付与されるもの: クリック計測リンク（UTM付き）、開封計測、配信停止リンク、送信者情報。
- 差し込み項目: `{{company_name}}` `{{name}}`
- チェック: 配信同意・配信停止・7日2通の頻度上限・同一資料の30日再送禁止・対象外リード。営業時間外は翌営業日9:00に予約されます。
- `schedule_at` で予約配信できます（配信時点のセグメント該当者に送信）。

## ポップアップ（ma_manage_popup）
| 表示条件 | 内容 |
|---|---|
| segment_id | 対象セグメント（例: 匿名でLPを2回以上閲覧） |
| url_contains / url_excludes | 表示するページ・除外するページ |
| audience | all / anonymous（未実名化のみ）/ identified |
| frequency / max_impressions | once_per_visitor / once_per_day / every_visit、最大表示回数 |
| show_after_seconds / start_at / end_at | 表示までの秒数、掲載期間 |
| hide_after_click | クリック後は表示しない（既定: true） |

`type: form` は資料DLフォームを、`type: banner` はセミナー告知などのリンクを表示します。`decide` で、特定の訪問者・URLに表示されるものを確認できます。

## Webプッシュ（ma_send_web_push）
- 対象は、ブラウザで通知を許諾した訪問者です（匿名客を含む）。セグメントで絞り込めます。
- 7日3回の頻度上限があり、営業時間外は翌営業日9:00に予約されます。
- リンク先URLにはUTM（例: `utm_source=ma_push&utm_medium=push`）を付けます。

## 報告ルール
`planned`＝計画（未配信）、`scheduled`＝予約、`blocked`＝ガードレールで停止、`sent`＝配信済み。
