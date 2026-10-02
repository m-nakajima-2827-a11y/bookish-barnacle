# サイト分析チェックリスト（8観点）

各項目は「確認方法」で事実を取り、判定します。確認できなかった項目は「未確認」と書き、推測で埋めません。

## 1. ファーストビュー・価値提案
| 確認項目 | 確認方法 | 課題の目安 |
|---|---|---|
| 誰向け・何のサービスかが3秒で伝わるか | PC/スマホのスクリーンショット | キャッチが抽象的（「未来を創る」等） |
| FV内にCTAがあるか | スクリーンショット | スマホFVにCTAなし |
| 実績・数字・権威付けの有無 | 本文確認 | 導入社数・事例・受賞などの記載なし |

## 2. CV導線
| 確認項目 | 確認方法 | 課題の目安 |
|---|---|---|
| トップ→CVまでのクリック数 | 実際に遷移 | 3クリック超 |
| CTAの数・位置・文言 | HTML・SS | ページ末尾のみ／「お問い合わせ」だけ |
| CVの選択肢 | 本文確認 | 問い合わせのみ（資料DL・相談予約・料金表がない） |
| フォーム項目数・必須数 | フォーム確認 | 項目10超、不要な必須項目 |
| 追従CTA・電話タップ | スマホSS | なし |

## 3. 情報設計・ナビゲーション
| 確認項目 | 確認方法 | 課題の目安 |
|---|---|---|
| グローバルナビの項目数・名称 | HTML | 8項目超、社内用語 |
| 料金・事例・FAQ ページの有無 | サイト内リンク | 比較検討に必要な情報がない |
| パンくず・内部リンク | HTML | なし |

## 4. コンテンツ・信頼性
| 確認項目 | 確認方法 | 課題の目安 |
|---|---|---|
| 導入事例・お客様の声 | 本文 | なし／数値のない事例 |
| 更新頻度 | お知らせ・ブログの日付 | 最終更新が6か月以上前 |
| 会社情報・プライバシーポリシー・SSL | 本文・URL | 不備あり |

## 5. SEO（内部対策）
| 確認項目 | 確認方法 | 課題の目安 |
|---|---|---|
| title | `<title>` | 全ページ同一、32文字超で要点が後半 |
| meta description | `<meta name="description">` | 未設定・重複 |
| h1 | `<h1>` | なし／複数／ロゴ画像のみ |
| 見出し構造 | h2〜h3 | 階層の飛び |
| 画像 alt | `<img alt>` | 未設定が多い |
| canonical・OGP・構造化データ | `<link rel="canonical">` 等 | 未設定 |
| sitemap.xml・robots.txt | `/sitemap.xml` `/robots.txt` | なし／誤ったブロック |

## 6. 表示速度（Core Web Vitals）
| 確認項目 | 確認方法 | 課題の目安 |
|---|---|---|
| LCP | PageSpeed Insights（mobile） | 2.5秒超 |
| CLS | 同上 | 0.1超 |
| INP | 同上（フィールドデータがある場合） | 200ms超 |
| 画像容量・形式 | HTML・レスポンスヘッダ | 500KB超の画像、WebP/AVIF未使用 |

PSI を取得できない場合は「推定」と明記し、数値を断定しない。

## 7. モバイル・アクセシビリティ
| 確認項目 | 確認方法 | 課題の目安 |
|---|---|---|
| viewport 設定 | `<meta name="viewport">` | なし |
| 文字サイズ・タップ領域 | スマホSS | 本文14px未満、ボタンが小さい |
| コントラスト | SS | 薄いグレー文字 |
| 横スクロール | スマホSS | 発生 |

## 8. 計測・運用
| 確認項目 | 確認方法 | 課題の目安 |
|---|---|---|
| GA4 / GTM タグ | HTML（`gtag/js?id=G-`、`googletagmanager.com/gtm.js`） | なし |
| CVイベント | サンクスページの有無 | サンクスページなし（計測困難） |
| 広告タグ | Meta Pixel 等 | 広告出稿中なのに未設置 |

## 取得コマンド例
```bash
# HTMLの主要タグを抽出
curl -sL <URL> -o page.html
grep -oiE '<title>[^<]*</title>' page.html
grep -oiE '<meta name="description"[^>]*>' page.html
grep -oiE '<h1[^>]*>.*?</h1>' page.html | head
grep -c '<img' page.html; grep -ciE '<img[^>]*alt=""' page.html
grep -oE 'G-[A-Z0-9]{6,}|GTM-[A-Z0-9]+' page.html | sort -u

# PageSpeed Insights（mobile）
curl -s "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=<URL>&strategy=mobile" \
  | python3 -c "import json,sys;d=json.load(sys.stdin)['lighthouseResult'];a=d['audits'];print('score',d['categories']['performance']['score']);[print(k,a[k]['displayValue']) for k in ['largest-contentful-paint','cumulative-layout-shift','total-blocking-time']]"
```

```python
# スクリーンショット（Playwright）
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, w, h in [("pc", 1440, 900), ("sp", 390, 844)]:
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto("<URL>", wait_until="networkidle")
        pg.screenshot(path=f"fv_{name}.png")
    b.close()
```
