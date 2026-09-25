---
name: sync-lead-activity
description: BtoBのリード行動履歴（Webサイト・LP閲覧、資料DL、ウェビナー申込・参加、メール、Instagram、広告クリック、問い合わせ、架電、商談設定、受注・失注）と企業属性（業界・従業員規模・役職・決算月）、メール同意状態をリード／企業単位に統合する。MA・CRM・フォームのデータ取り込み、商談ステータスの反映に使う。
---

# ① リード行動データ統合（sync_lead_activity）

## 実行方法
```bash
python -m dm_agent call sync_lead_activity '<JSON または .json パス>' [--client <client_id>]
```
スキーマ: `schemas/sync_lead_activity.json`

```json
{
  "lead_id": "L101",
  "account": {"account_id": "A-MFG-01", "industry": "manufacturing", "employee_band": "50-299", "job_role": "sales_manager"},
  "consent": {"email_opt_in": true},
  "touchpoints": [
    {"channel": "landing_page", "timestamp": "2026-09-07T20:30:00+09:00", "event_type": "whitepaper_download",
     "payload": {"asset_id": "WP-MFG-01", "landing_page": "/lp/mfg-checksheet",
                 "utm": {"source": "instagram", "medium": "social", "campaign": "mfg_paper", "content": "profile_link"}}}
  ]
}
```

## payload の取り決め
| event_type | 主なキー |
|---|---|
| whitepaper_download / webinar_registration / webinar_attendance / case_study_view | `asset_id`（`config/clients/*.json` の content_library） |
| page_view / pricing_page_view | `url` または `landing_page` |
| 流入を伴うイベント | `utm`（source / medium / campaign / content）, `landing_page` |
| meeting_booked / deal_won | `amount`（商談見込額・受注額、円） |
| deal_lost | `lost_reason`（`timing` / `budget` / `competitor` / `no_need` 等） |

## 自動で起きること（自動化ルール有効時）
- 資料DL・セミナー申込・問い合わせ、またはセミナー参加・料金ページ閲覧・事例閲覧 → **即時にスコアを再計算**
- 商談設定・受注 → 広告の除外リスト（商談中・既存顧客）を同期
- 失注（`timing` / `budget`）→ 予算編成時期の再アプローチタスクを作成

## 注意
- 氏名・メールアドレス・電話番号は入れず、MA/CRMのIDと企業属性だけを渡します。
- 同一イベントは重複として除外されます（再送しても安全です）。
- 流入元（first_touch）は、UTMまたはLPを含む最初のイベントで決まります。広告・SNSのリンクは必ずUTM付きにしてください。
