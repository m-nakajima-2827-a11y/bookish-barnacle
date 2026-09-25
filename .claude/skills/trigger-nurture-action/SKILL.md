---
name: trigger-nurture-action
description: BtoBリードの育成と営業連携を実行する。業界別（IT・製造業・汎用）の育成メールシナリオ登録、メール配信、ウェビナー招待、次に読むべき資料の推奨、インサイドセールスへの引き渡し（初回接触30分ルールつきCRMタスク）、失注・保留リードの予算編成時期に合わせた再アプローチ予約に使う。
---

# ③ リード育成・営業引き渡し（trigger_nurture_action）

## action 一覧
| action | 用途 | 主な入力 |
|---|---|---|
| enroll_nurture_track | MQLを業界別シナリオへ登録（例：製造業は 資料送付→3日後 事例→10日後 セミナー→20日後 診断案内） | `nurture_track`（省略時は業界から自動選択） |
| send_email | 単発メール | `content_asset_id`, `payload_details.subject / body` |
| invite_webinar | セミナー招待 | `content_asset_id`（省略時は既定セミナー） |
| recommend_content | 未読資料から次に案内すべきものを提案（送信はしない） | - |
| sales_handoff | ホットリードをインサイドセールスへ（CRMタスク） | `payload_details.handoff_note` |
| schedule_recontact | 再アプローチのタスクを予約 | `payload_details.recontact_date`（省略時は決算月から推定） |

```bash
python -m dm_agent call trigger_nurture_action '{"lead_id":"L101","action":"sales_handoff"}'
```

## ガードレール（`config/policy.json`）
| チェック | 既定値 | 結果 |
|---|---|---|
| メール配信同意・配信停止 | 必須 | `blocked`（特定電子メール法。配信停止リンク・送信者情報は自動で付与） |
| 頻度上限 | 7日で2通 | `blocked` |
| 同一資料の再送 | 30日以内は不可 | `blocked` |
| 配信時間 | 平日9:00〜18:00（年末年始は休業） | `scheduled`：翌営業日9:00 |
| 営業引き渡し | ホットリードのみ | それ以外は `blocked`（先にスコアリング） |
| 初回接触期限 | 営業時間内で30分 | CRMタスクの `due_at` に設定 |

## 引き渡しタスクに含まれる情報
業界・規模・役職、スコア、最初の流入元（UTM）、直近の行動6件、閲覧した資料、同一企業の関与人数、会話のきっかけ案（閲覧履歴からの**仮説**）。

## 再アプローチ時期の考え方
決算月（未登録なら3月）から期初を求め、その3か月前の月初を「予算編成時期」と**仮定**してタスクを作成します。顧客から時期を聞けている場合は `recontact_date` を指定してください。

## 注意
- SQL以降に進んだリードの育成メールは自動で停止します（営業と二重に接触しないため）。
- メール本文のテンプレートは下書きです。本番前にクライアントの確認を受けてください。
