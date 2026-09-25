---
name: build-utm-tracking-url
description: GA4で流入元を正しく計測するためのUTMパラメータ付きURL（計測用URL）を作成・検証する。Instagramのプロフィールリンク・ストーリーズ・投稿・広告、メルマガ、セミナー招待、検索広告などの設置場所ごとに、小文字統一・全角禁止などの命名ルールをチェックし、GA4でのチャネル分類を予測してキャンペーン台帳に登録する。
---

# ⑤ UTM付きURLの作成（build_utm_tracking_url）

## 実行方法
```bash
python -m dm_agent call build_utm_tracking_url '{
  "base_url":"https://example.com/lp/mfg-checksheet",
  "utm_source":"instagram","utm_medium":"social","utm_campaign":"mfg_paper",
  "placement":"instagram_profile","target_industry":"manufacturing"}'
```

## 入力項目
| 項目 | 意味 | 例（Instagram運用） |
|---|---|---|
| base_url | リンク先ページ | https://example.com/lp/mfg-checksheet |
| utm_source | どこから来たか（媒体名） | instagram |
| utm_medium | どうやって来たか（種類） | social（通常投稿）/ paid_social（広告） |
| utm_campaign | どの企画か | mfg_paper（製造業向け資料）/ it_seminar（IT企業向けセミナー） |
| utm_content | 設置場所・クリエイティブの区別 | 省略時は placement から自動設定（profile_link_manufacturing, story_it_saas 等） |
| placement | 設置場所 | instagram_profile / instagram_story / instagram_post / instagram_ad / email_newsletter / webinar_invite / search_ad |

## 検証ルール
- **エラー（URLを発行しない）**: 大文字（GA4では `Instagram` と `instagram` が別集計になる）、全角・日本語、空白、記号
  - 自動で直せる場合は `suggested_url` を返します。日本語を含む場合は意味が変わるため `needs_manual_fix` として手動での命名を求めます。
- **警告**: 命名辞書（`config/clients/<client>.json` の utm_dictionary）にない source / medium、媒体と medium の組み合わせが推奨外（例: instagram に referral）、utm_content 未設定
- `predicted_ga4_channel_group` で、GA4の既定チャネル（Organic Social / Paid Social / Paid Search / Email 等）のどれに入るかを確認できます（主要ケースを簡略化した判定です）。

## 運用のコツ
- フィード投稿のキャプション内のURLはクリックできません。「プロフィールのリンクから」と誘導し、プロフィールリンクにUTM付きURLを設定します。
- URLが長い場合は、リンク集ツールや短縮URLの遷移先にUTM付きURLを設定します。
- 発行したURLはキャンペーン台帳に登録され、`analyze-marketing-funnel` の表記ゆれ点検に使われます。
