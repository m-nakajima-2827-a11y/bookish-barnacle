"""SKILL.md・references・examples・scripts から、エージェント用の1ファイル版
.claude/agents/website-improvement-agent.md を組み立てる。

スキル側のファイルを更新したら、リポジトリのルートで実行して同期する:
    python .claude/skills/website-improvement-proposal/scripts/build_agent.py
"""
import re
base = '.claude/skills/website-improvement-proposal/'
r = lambda p: open(base + p, encoding='utf-8').read()

def fence_map(t, f):
    out, inside = [], False
    for line in t.split('\n'):
        if line.startswith('```'):
            inside = not inside
        out.append(line if inside else f(line))
    return '\n'.join(out)

skill = r('SKILL.md')
desc = skill.split('description: ', 1)[1].split('\n', 1)[0]
body = skill.split('---\n', 2)[2].replace('# WEBサイト改善提案（website-improvement-proposal）\n\n', '', 1)
subs = [
    ('`references/analysis-checklist.md` の8観点', '**付録A「サイト分析チェックリスト」**の8観点'),
    ('原稿は `examples/sample-deck.json` と同じ構造の JSON', '原稿は**付録C「原稿JSONの記入例」**と同じ構造の JSON'),
    ('PowerPointの見せ方（書体・級数・配色・配置）は `references/design-rules.md` に固定します。', 'PowerPointの見せ方（書体・級数・配色・配置）は**付録B**に固定します。'),
    ('   python .claude/skills/website-improvement-proposal/scripts/build_deck.py <原稿.json> <出力.pptx>', '   python build_deck.py <原稿.json> <出力.pptx>'),
    ('2. 生成スクリプトを実行。', '2. 生成スクリプトを用意して実行。`.claude/skills/website-improvement-proposal/scripts/build_deck.py` があればそれを使い、なければ**付録D**のコードを作業ディレクトリに `build_deck.py` として保存してから実行する。'),
    ('デザイン仕様の詳細は `references/design-rules.md` を参照。', 'デザイン仕様の詳細は**付録B「PowerPointデザイン仕様」**を参照。'),
    ('確認は1回にまとめ、最大3問までにします（AskUserQuestion が使える場合はそれを使う）。', '確認は1回にまとめ、最大3問までにします。'),
    ('- 「なし」「OK」「進めて」等 → Step 5 へ。', '- サブエージェントとして実行中でユーザーに直接質問できない場合は、この確認ブロックを最終出力として返して**いったん終了**する。呼び出し元から回答付きで再開されたら続きを行う。\n- 「なし」「OK」「進めて」等 → Step 5 へ。'),
    ('4. `.pptx` をユーザーへ送付（SendUserFile が使える場合はそれを使う）。', '4. `.pptx` の保存先パスを報告する（ファイル送付ツールが使える場合は送付する）。'),
    ('1. 原稿 JSON を作業ディレクトリ（スクラッチパッド推奨）に保存。', '1. 原稿 JSON を作業ディレクトリに保存。'),
    ('`scripts/build_deck.py` はこの仕様どおりに出力します。', '付録Dの生成コードはこの仕様どおりに出力します。'),
]
for a, b in subs:
    assert a in body or a.startswith('`scripts/'), a
    body = body.replace(a, b)

def appendix(p):
    t = re.sub(r'^# .*\n\n?', '', r(p), count=1)
    t = t.replace('`scripts/build_deck.py` はこの仕様どおりに出力します。', '付録Dの生成コードはこの仕様どおりに出力します。')
    return fence_map(t, lambda l: re.sub(r'^(#{2,5}) ', r'#\1 ', l))

leftover = [l for l in body.splitlines() if 'references/' in l or 'examples/' in l]
assert not leftover, leftover

out = f'''---
name: website-improvement-agent
description: {desc}
tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch
---

# WEBサイト改善提案エージェント

このファイルだけで動くように、スキル本体・分析チェックリスト・デザイン仕様・原稿の記入例・PowerPoint生成コードをまとめています。

## 実行環境
- 必要なもの: Python 3、`python-pptx`（未導入なら `pip install python-pptx`）
- フォント: Noto Sans JP Medium（Google Fonts の静的フォント NotoSansJP-Medium を、資料を開くPCにもインストールしておく）
- あれば使うもの: WebFetch または `curl`（サイト取得）、Playwright + Chromium（スクリーンショット）、PageSpeed Insights API（表示速度）、LibreOffice Impress と `pdftoppm`（生成後のプレビュー確認）
- 作業ファイル（取得したHTML、スクリーンショット、原稿JSON、pptx）は作業用ディレクトリにまとめ、リポジトリには置かない。
- 使えないツールがある場合は、代わりの方法で進め、その旨と影響（例:「表示速度は推定」）を報告に明記する。

## 起動時の入力
- 必須: 対象URL
- 任意: サイトの目的・CV、ターゲット、現状数値、競合URL、制約（予算・CMS・期限）、提出先・作成者

## 最終報告の内容
1. 分析サマリーと採用した改善提案（3〜5点）
2. 生成した `.pptx` の保存先パス
3. 未確認の項目、仮説で置いた前提、ユーザーに確認が必要な事項

---
{body}
---

## 付録A. サイト分析チェックリスト
{appendix('references/analysis-checklist.md')}
---

## 付録B. PowerPointデザイン仕様
{appendix('references/design-rules.md')}
---

## 付録C. 原稿JSONの記入例
- 文字列中の `**...**` は金色（アクセント色）で強調される。
- `proposals` は3〜5件。各提案の右側は `chart`（棒/折れ線）か `metric`（大きな数字1つ）のどちらか。
- `metric.value` は数字だけを入れ、単位は `unit` に分ける（例: `"value": "4.8", "unit": "秒"`）。
- 以下の数値はすべて記入例。実案件では実測値に置き換える。

```json
{r('examples/sample-deck.json').rstrip()}
```

---

## 付録D. PowerPoint生成コード（build_deck.py）
作業ディレクトリに `build_deck.py` として保存し、`python build_deck.py <原稿.json> <出力.pptx>` で実行する。

```python
{r('scripts/build_deck.py').rstrip()}
```
'''
open('.claude/agents/website-improvement-agent.md', 'w', encoding='utf-8').write(out)
print('ok', out.count('\n'))
