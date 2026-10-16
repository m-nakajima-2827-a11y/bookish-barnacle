---
name: ma-tracking-and-customers
description: 自社開発MA（SATORIの機能構成に準拠）の計測とカスタマー管理。Webサイト訪問者を匿名客のまま記録し（アンノウンマーケティング）、Webアクセス・メール開封/クリック・配信停止・ポップアップ・Webプッシュの行動をスコア・セグメント・シナリオに反映する。カスタマーの参照・検索・属性更新・タグ付与・配信停止・同意記録にも使う。
---

# MA: 計測・カスタマー管理（ma_track_activity / ma_manage_customer）

## 計測（ma_track_activity）
サイトの計測タグ・メールのトラッキングから届く行動を記録します。

```bash
python -m dm_agent call ma_track_activity '{"visitor_id":"ck-101","events":[
  {"type":"web_access","timestamp":"2026-09-02T21:00:00+09:00",
   "url":"https://example.com/lp/mfg-checksheet?utm_source=instagram&utm_medium=social&utm_campaign=mfg_paper"}]}'
```

| type | 主な入力 | 何が起きるか |
|---|---|---|
| web_access | visitor_id, url | URLからUTMを抽出し、スコア加算（共通+5、個別設定があればその点数）。実名客ならリードにも連携（料金ページ・事例ページは高意図イベントとして扱う） |
| email_open / email_click / unsubscribe | email_token | 開封+1 / クリック+10 / 配信停止−30。配信停止はMAとリードの両方に反映 |
| popup_view / popup_click | visitor_id, popup_id | ポップアップの表示・クリック実績 |
| push_permission / push_click | visitor_id, granted / push_id | Webプッシュの許諾・クリック |

- 実行のたびにセグメントを判定し、新たに該当したセグメントを起点とするシナリオを起動します。
- 最後の web_access のURLに対して、表示すべきポップアップを返します（`popup`）。

## カスタマー管理（ma_manage_customer）
| action | 用途 |
|---|---|
| get | 詳細（スコア・タグ・セグメント・直近の行動・スコア履歴） |
| search | タグ・セグメント・最低スコア・実名/匿名で検索 |
| update_attributes | 会社名・業種・規模・役職・決算月など（リードの企業属性にも反映） |
| add_tag / remove_tag | タグ付与・削除（タグ付与を起点とするシナリオが動く） |
| unsubscribe | 配信停止 |
| record_opt_in | メール配信の同意を記録（`opt_in_evidence` に取得経路・日時が必須） |

## 守ること
- 連絡先（メールアドレス・氏名・電話番号）は出力・ログで常にマスクされます。マスクを外す手段を探さないでください。
- 同意は本人の意思表示に基づくものだけを記録します。配信停止したカスタマーを手動で同意に戻すことはできません。
