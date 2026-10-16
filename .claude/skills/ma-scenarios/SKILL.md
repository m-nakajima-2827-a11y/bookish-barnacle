---
name: ma-scenarios
description: 自社開発MA（SATORIの機能構成に準拠）のシナリオ。セグメント該当・フォーム送信・タグ付与をトリガーに、ステップメール（N日後）、タグ付与・削除、社内通知（Webhook・CRMタスク）を自動実行する。業界別の育成シナリオ、スコア到達時の営業通知、セミナー申込者のフォローなどの作成・開始・停止・確認に使う。
---

# MA: シナリオ（ma_manage_scenario）

## 定義
```json
{"name":"セミナー申込者フォロー",
 "trigger":{"type":"form_submitted","key":"F-SEMINAR"},
 "steps":[{"day":1,"action":"send_email","email":{"subject":"セミナー前にご覧ください：導入事例","asset_id":"CS-MFG-01"}},
          {"day":7,"action":"add_tag","tag":"seminar_followed"},
          {"day":7,"action":"notify","notify":{"channel":"webhook","to":"https://hooks.example.com/slack/sales","message":"セミナー後フォロー対象"}}],
 "exit_conditions":{"lead_stages":["sql","opportunity","customer","disqualified"],"tags":["contact"]},
 "allow_reentry":false}
```

| 項目 | 内容 |
|---|---|
| trigger.type | segment_entered（セグメントに新たに該当）/ form_submitted / tag_added / manual（育成シナリオなど他スキルから登録） |
| steps[].day / hour | 登録時点からの経過日数・時間 |
| steps[].action | send_email / add_tag / remove_tag / notify（webhook・crm_task） |
| exit_conditions | リードのステージ・タグ・セグメントに該当したら、以降のステップを止める（営業対応中への二重接触を防止） |
| skip_if_consumed | 送る資料が閲覧・DL済みならそのステップを飛ばす（育成シナリオで使用） |

## 運用手順
1. `create` → 下書き（draft）で保存されます。
2. 件名・本文・日数・離脱条件を確認します。
3. `activate` で開始します。停止は `pause` です。
4. `get` / `list` で登録中・完了・離脱の人数を確認します。

## 既定シナリオ
- `nurture_manufacturing` / `nurture_it_saas` / `nurture_general`: 業界別の育成メール（`trigger-nurture-action` の enroll_nurture_track から登録）
- `SC-SCORE-ALERT`: スコア100到達 → タグ付与＋営業チャンネルへ通知
- `SC-SEMINAR-FOLLOW`: セミナー申込の翌日に事例を案内

メールのステップには、同意・配信停止・頻度上限・営業時間のチェックが自動で適用されます。
