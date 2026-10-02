# WEBサイト改善提案キット

URLを渡すと、サイトを分析して改善提案（3〜5点）を作ります。内容を確認したうえで、1提案1枚の提案書（PowerPoint）を作成します。

## 同梱ファイル
| ファイル | 用途 |
|---|---|
| `.claude/agents/website-improvement-agent.md` | **エージェント用の1ファイル版**。手順・チェックリスト・デザイン仕様・記入例・生成コードをすべて含む |
| `.claude/skills/website-improvement-proposal/SKILL.md` | スキル本体（手順・出力ルール・固定フォーマット・品質チェック） |
| `.claude/skills/website-improvement-proposal/references/analysis-checklist.md` | サイト分析の8観点とコマンド例 |
| `.claude/skills/website-improvement-proposal/references/design-rules.md` | PowerPointのデザイン仕様（書体・級数・配色・配置） |
| `.claude/skills/website-improvement-proposal/scripts/build_deck.py` | 原稿JSONから .pptx を作る生成コード |
| `.claude/skills/website-improvement-proposal/examples/sample-deck.json` | 原稿JSONの記入例 |
| `.claude/skills/website-improvement-proposal/scripts/build_agent.py` | スキル側の更新をエージェント用1ファイル版に反映するスクリプト |
| `.claude/skills/website-improvement-proposal/examples/sample.pptx` | 記入例から生成したサンプル（8枚） |
| `.claude/skills/website-improvement-proposal/examples/sample-preview.pdf` | サンプルのPDFプレビュー（代替フォントで表示） |

エージェントとして使う場合は `website-improvement-agent.md` だけで動きます。スキルとして使う場合は `.claude/skills/website-improvement-proposal/` フォルダを使います。

## 導入方法
1. このリポジトリを開けば、そのまま使えます。別のプロジェクトで使う場合は、`.claude/agents/website-improvement-agent.md` と `.claude/skills/website-improvement-proposal/` を、そのプロジェクトの `.claude/` にコピーします。
2. Python 3 と `python-pptx` を用意します。
   ```bash
   pip install python-pptx
   ```
3. Noto Sans JP Medium をインストールします（Google Fonts の太さ別ファイル `NotoSansJP-Medium`）。提案書を開くPCにも必要です。

## 使い方
```
website-improvement-agent で https://example.co.jp/ の改善提案書を作って
```
1. サイトを分析し、課題を洗い出し、改善提案を3〜5点に絞ります。
2. 「変更・修正・追加はありますか？」と確認します。「なし」と答えるまで提案書は作りません。
3. 原稿を作り、PowerPointを生成します。

## 更新するとき
スキル側（`SKILL.md`・`references/`・`examples/`・`scripts/build_deck.py`）を直したら、エージェント用の1ファイル版に反映します。
```bash
python .claude/skills/website-improvement-proposal/scripts/build_agent.py
```
デザインを変えた場合は、サンプルも作り直します。
```bash
python .claude/skills/website-improvement-proposal/scripts/build_deck.py \
  .claude/skills/website-improvement-proposal/examples/sample-deck.json \
  .claude/skills/website-improvement-proposal/examples/sample.pptx
```

## 生成コードだけを使う場合
```bash
python .claude/skills/website-improvement-proposal/scripts/build_deck.py 原稿.json 出力.pptx
```

## デザイン
- 書体: Noto Sans JP Medium（太字なし。強調は金色）
- 配色: 紺 `#1F3A5F`・金 `#9A6F2E`・緑 `#256B64`
- 表紙と締めは紺の背景、本文スライドは白
- 詳細は `design-rules.md` を参照

## ご注意
- サンプルの数値はすべて記入例です。実際の案件では実測値に置き換えてください。
- `examples/sample-preview.pdf` は Noto Sans JP Medium の代わりに Noto Sans CJK JP（標準の太さ）で表示しています。実際の表示より文字が細く見えます。
- 資料を開くPCに Noto Sans JP Medium が無いと、別の書体で表示されます。社外に渡す場合はPDFにして送るのが確実です。
