---
name: analyze-marketing-funnel
description: GA4の流入データ、サーチコンソールの検索クエリ、MA/CRMのリード・商談データを統合し、流入元・キャンペーン・LP・業界別に「セッション→資料DL→MQL→SQL→商談→受注」のファネルと商談金額を分析する。UTMの表記ゆれ、UTMなしのLP流入、指名検索の推移、初回接触までの時間も点検し、改善提案付きの月次レポートを作成する。「リードが少ない」「商談化しない」の原因分析に使う。
---

# ⑦ マーケティングファネル分析（analyze_marketing_funnel）

## 実行方法
```bash
python -m dm_agent call analyze_marketing_funnel '{"period_start":"2026-09-01","period_end":"2026-09-30","group_by":"source_medium"}'
```

| group_by | 用途 |
|---|---|
| channel_group | GA4の既定チャネル単位の全体像 |
| source_medium | Instagram・検索広告・メール等の媒体比較 |
| campaign | キャンペーン（utm_campaign）単位の比較 |
| landing_page | キャンペーンLPごとのCVR比較（LP改善の提案が出るのはこの軸と campaign のみ） |
| industry | IT・製造業など業界別の商談化（セッションは集計対象外） |

`attribution_model`: 商談金額を、どの接点にどれだけ配分するか（`first_touch`＝リード創出元〔既定〕／`last_touch`／`linear`／`position_based`）。

## 出力の主な項目
- ファネル表: セッション、CVR、リード、MQL、ホット、SQL、商談、受注、SQL率、商談金額、広告費、CPL、商談化単価
- `utm_hygiene`: 大文字・日本語の混入、表記ゆれ（Instagram／instagram）、UTMのないLP流入、命名辞書にない medium
- `first_contact_sla`: 営業引き渡しから初回接触までの中央値・期限超過・未接触
- `search_console`: 指名検索クリックの前半・後半比較、順位は高いがCTRが低いクエリ（タイトル改善候補）
- `recommendations`: 優先度付きの改善提案

## レポート作成時の構成
1. サマリー（リード・SQL・商談金額・広告費）
2. ファネル表（出力をそのまま使用）
3. 課題と原因（「リードが少ない」＝集客・LP側、「商談化しない」＝対象者のずれ・育成・初回接触の速さ、に分けて整理）
4. 改善提案（優先度・担当・時期）
5. 計測の修正事項（UTM）

## 注意
- 指名検索の増加とSNS施策の関係は、同時期の他施策も影響するため「仮説」として書きます。
- リード数が少ない場合、率の比較は参考値です（出力の注記に従ってください）。
- 本番のデータ取得は、GA4 Data API（またはBigQueryへのエクスポート）、Search Console API、MA/CRMのAPIに接続します（`README.md` 参照）。
