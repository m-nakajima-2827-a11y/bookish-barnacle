# 月次SEO分析（毎月3日 8:47 JST 自動実行）

実行者: AI社員 `growx-ai-employee` ／ Skill: `growx-web-automation`（ステップ1・2・3・7・8）
対象期間: 前月1日〜末日（GSCの反映遅れを考慮し3日に実行）

## 手順
1. **入力確認（ステップ0）**
   - `growcross/data/gsc/` と `growcross/data/ga4/` に前月分のCSVがあるか確認します。なければ該当KPIを「データ未取得」とし、報告の「不足データ」に記載します。
2. **サイト・既存記事の分析（ステップ1）**
   - `https://www.grow-cross.com/sitemap.xml`（なければ主要ページ）を読み、`growcross/content/existing-articles.csv`（URL｜タイトル｜公開日｜領域｜主KW｜CTA有無）を更新します。
   - calendar.csv で「ChatGPT登録待ち」だった記事が公開されていれば、状態を「公開済み」にし公開URLを記録します。
3. **自社の検索状況（ステップ7）**
   - ラッコキーワード `influx-statistics` `influx-trend` `influx-keywords`（www.grow-cross.com）で獲得KW数・推定流入を取得します。
   - 公開済み記事の主KWについて `search-rank-history` で順位を測ります（非同期: status → results）。
   - `influx-aio` で AIによる概要での引用状況を確認します。
4. **競合SEO調査（ステップ2）**
   - `profile.md` の競合（未記載なら `competitive` で抽出した上位3〜5ドメイン）について `influx-keywords` `influx-pages` を取得し、競合SEO分析表を作成します。
   - 取得結果のCSV/JSONは `growcross/data/rakko/YYYY-MM_*.json` に保存し、同月内の再取得を避けます。
5. **重複・優先順位の判定（ステップ3）**
   - 競合が獲得しGrowXが未獲得のKWと既存記事を照合し、重複判定表を作成します。`keyword-map.md` を更新します。
6. **改善提案（ステップ8）**
   - 11〜20位の記事、GSCで表示回数が多くCTRが低い記事をリライト候補にします。
   - calendar.csv の今後6か月分を見直し、入れ替え案を作ります（calendar.csv の変更は「提案」欄に書き、確定は承認後）。
7. **月次改善レポート**: `growcross/reports/monthly-seo_YYYY-MM.md`
   - growcross-reporting の12ページ構成で、各ページに「タイトル・要点・詳細・図表案」を記載します。
   - 前月レポートがあれば前月比を併記します。試算は「想定」と明記します。

## 保存と共有
- 作業ブランチ `growx-ops` を最新化して作業し、コミットして `growx-ops` にpushします。
- 最後に、レポートの要点（KPI・課題・来月の重点・承認依頼・不足データ）を報告します。

## やらないこと
- WordPressへの登録・公開、リダイレクト設定、既存記事の書き換え
- データのない数値の推測・補完
