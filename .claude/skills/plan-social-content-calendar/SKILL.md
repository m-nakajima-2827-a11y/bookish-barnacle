---
name: plan-social-content-calendar
description: BtoB向けInstagramの投稿カレンダーを作成する。IT企業向け・製造業向けにテーマを分け、保存を狙う図解カルーセル（月）、中の人リール（水）、導入事例（金）、ウェビナー告知ストーリーズを割り当て、資料DLへのUTM付き導線と投稿ごとのKPIを設定する。新規アカウントではプロフィール設計のチェックリストも出す。
---

# ⑥ Instagram投稿カレンダー（plan_social_content_calendar）

## 実行方法
```bash
python -m dm_agent call plan_social_content_calendar '{
  "start_date":"2026-10-05","weeks":4,"posting_days":["mon","fri"],
  "target_industries":["manufacturing","it_saas"],"account_status":"new"}'
```

## 設計の考え方
| 軸 | 内容 |
|---|---|
| プロフィール | 業界共通の課題でまとめる（例:「中小企業の営業組織を仕組み化する営業コンサル」）。ハイライトは「IT企業の実績」「製造業の実績」「セミナー」に分ける |
| 投稿 | 業界ごとにテーマを分けて交互に配信（IT: トス上げ基準・解約率とCS連携 ／ 製造業: ベテラン営業のノウハウのマニュアル化・提案型営業への転換） |
| 形式 | 図解カルーセル＝保存数と新規リーチ、事例＝信頼形成と指名検索、リール＝専門性と親近感、ストーリーズ＝セミナー集客 |
| 導線 | 投稿 → プロフィールのリンク（業界別UTM付き）→ 業界別LP → 資料DL（リード獲得）→ GA4とMAで測定 |

テーマ一覧・曜日パターン・プロフィールのチェックリストは `config/clients/<client>.json` の `social` で編集できます。

## 出力
- `entries`: 日付・形式・対象業界・テーマ・目的・KPI・CTA・遷移先URL（UTM付き）・制作メモ
- `profile_links`: 業界別のプロフィール用URL（リンク集ツールに設定）
- `monthly_kpis`: 一次成果（保存数、プロフィールアクセス率、リンククリック）と最終成果（資料DL、セミナー申込、商談獲得）
- `profile_setup_checklist`（account_status が new のとき）

## 使い方の注意
- 出力はテーマと構成の案です。投稿文・デザインは、この出力をもとに作成してください（LPとデザインのトーンを揃える）。
- 事例投稿の数値は、顧客の了承を得た実績だけを載せます。
- 月次で `analyze-marketing-funnel` を実行し、`instagram / social` の資料DL・SQL・商談につながっているかを確認します。
