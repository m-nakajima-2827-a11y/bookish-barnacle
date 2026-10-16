---
name: ma-segments-and-scoring
description: 自社開発MA（SATORIの機能構成に準拠）のセグメントとスコア定義。ページ閲覧・UTM・メール反応・フォーム送信・タグ・スコア・属性・匿名/実名・プッシュ許諾・配信同意・リードステージを組み合わせたセグメントの作成と試算、アクション種別ごとの共通スコアと特定URL・パラメータ・フォーム・タグ・セグメントの個別スコアの設定に使う。
---

# MA: セグメント・スコア定義（ma_manage_segment / ma_configure_scoring）

## スコア定義（ma_configure_scoring）
| 区分 | 内容 | 既定値 |
|---|---|---|
| 共通設定 | アクション種別ごとの加減点 | Webアクセス+5、メール内リンククリック+10、メール開封+1、配信停止−30（SATORIの公開FAQの既定値に準拠）。フォーム送信・ポップアップクリック・プッシュクリックは0（本実装での追加） |
| 個別設定 | `web_access`（url_filter / param_filter）、`form_submit`（form_id）、`tag_added`（key=タグ）、`segment_entered`（key=セグメント） | サンプル: 料金ページ+20、事例+10、問い合わせ+50、セミナー申込+30、資料DL+20 |

- 個別設定に該当したWebアクセスは、個別設定の点数を適用し、共通設定は加算しません。
- 点数は±100,000以内の整数です。変更は今後のアクションから適用されます（過去分は再計算しません）。
- `distribution` で実名客・匿名客のスコア分布を確認できます。

## セグメント（ma_manage_segment）
条件は `all` / `any` / `not` で組み合わせます。

| type | 例 |
|---|---|
| page_view | `{"type":"page_view","url_contains":"/price","min_count":1,"within_days":30}` |
| utm | `{"type":"utm","match":{"source":"instagram","campaign":"mfg_paper"}}` |
| email_open / email_click / form_submit / popup_click / push_click | `{"type":"form_submit","match":{"form_id":"F-SEMINAR"},"within_days":60}` |
| tag / score / attribute | `{"type":"tag","has":"dl_wp_mfg"}`, `{"type":"score","gte":100}`, `{"type":"attribute","field":"industry","equals":"manufacturing"}` |
| identified / push_subscribed / email_opt_in | 匿名・実名、プッシュ許諾、配信可 |
| lead_stage | `{"type":"lead_stage","in":["mql","hot"]}`（CRM・スコアリングと連動） |

- まず `preview` で人数（実名・匿名の内訳）を確認してから `create` します。
- 作成・更新した時点で既に該当している人には、シナリオを起動しません（過去分の一斉配信を防ぐため）。
- 既定セグメント: 匿名でLPを2回以上閲覧、料金ページ閲覧、スコア100以上、業種別×配信可、プッシュ許諾者。
