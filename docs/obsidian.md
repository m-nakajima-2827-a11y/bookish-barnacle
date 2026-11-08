# Obsidian 連携

エージェントが持つリード・企業・キャンペーン・タスク・レポートを、Obsidian の Vault に Markdown ノートとして書き出します。Obsidian の Vault は Markdown ファイルのフォルダなので、プラグインや API を使わずに連携できます。

## 使い方

```bash
# デモを実行し、その結果を Vault に書き出す
python -m dm_agent demo --obsidian-vault ~/Obsidian/MyVault

# 保存済みの状態（state/<client_id>.json）を書き出す。期間を指定するとファネル分析レポートも出力
python -m dm_agent obsidian-export --vault ~/Obsidian/MyVault --client sample_sales_consulting \
  --period-start 2026-09-01 --period-end 2026-09-30

# 環境変数で Vault を指定することもできます
export OBSIDIAN_VAULT=~/Obsidian/MyVault
python -m dm_agent obsidian-export --scenario   # サンプルデータで動作確認
```

書き出し先フォルダは `--folder`（`demo` では `--obsidian-folder`）で変更できます（既定: `DM Agent`）。

Python から使う場合:

```python
from dm_agent.obsidian import export_to_obsidian
export_to_obsidian(rt, "~/Obsidian/MyVault", funnel_reports=[report])
```

## 出力されるノート

| ノート | 内容 | 主なプロパティ |
|---|---|---|
| `00_ダッシュボード.md` | ステージ別リード数、優先対応（ホット・SQL）、各一覧へのリンク、Dataview クエリ例 | `client` |
| `リード/<lead_id>.md` | ステージ、企業属性、スコア、初回・最終接点、閲覧コンテンツ、引き渡し、商談、タスク、ステージ履歴、行動履歴（直近20件） | `stage`, `industry`, `job_role`, `fit`, `engagement`, `grade`, `first_touch_campaign`, `last_seen` |
| `企業/<account_id>.md` | 関与している担当者（購買関与者）と商談金額 | `industry`, `contacts`, `pipeline_amount` |
| `キャンペーン/<utm_campaign>.md` | UTM 付き計測用URL、初回接点がそのキャンペーンのリード | `utm_campaign`, `first_touch_leads` |
| `タスク.md` | CRM タスク（初回接触・再アプローチ・MA通知） | － |
| `レポート/ファネル分析 <期間>.md` | `analyze_marketing_funnel` の Markdown レポート | `period_start`, `period_end`, `group_by` |

- ノート同士は `[[wikilink]]` でつながっているため、グラフビューやバックリンクで「キャンペーン → リード → 企業」をたどれます。
- タグ（`dm-agent/lead`, `stage/sql`, `industry/manufacturing` など）で絞り込めます。
- タスクは [Tasks](https://github.com/obsidian-tasks-group/obsidian-tasks) プラグインの書式（`- [ ] … 📅 2026-09-10 ⏫`）です。プラグインがなくても通常のチェックリストとして表示されます。
- ダッシュボードの Dataview ブロックは、[Dataview](https://github.com/blacksmithgu/obsidian-dataview) プラグインを導入した場合のみ表として表示されます。

## 再エクスポートとメモ欄

- 書き込むのは Vault 内の書き出し先フォルダだけです。それ以外のノートには触れません。
- 各ノートの `<!-- dm-agent:begin -->` 〜 `<!-- dm-agent:end -->` の間はエクスポートのたびに上書きされます。
- `<!-- dm-agent:end -->` より後ろ（「メモ」欄）は保持されます。営業メモや商談の所感はここに書いてください。
- フロントマター（プロパティ）もエクスポートのたびに作り直されます。独自のプロパティは追加しないでください。
- 内容が変わらないノートは書き換えません（同期ツールの差分を最小化するため）。

## 個人情報の扱い

氏名・メールアドレス・電話番号は書き出しません。リードは ID と企業属性（業界・規模・役職）で表します。Vault を同期・共有する場合も、この方針を前提にしてください。

## Vault との同期方法

| 方法 | 向いている使い方 |
|---|---|
| PC 上で直接実行（`--vault` に Vault のパスを指定） | 最も簡単です。Obsidian Sync・iCloud・Dropbox 等で同期している Vault でもそのまま使えます |
| Git 経由（Vault を Git リポジトリにし、Obsidian Git プラグインで pull） | サーバーや CI で定期実行し、結果を Vault に反映したい場合 |
| Claude Code（クラウド）＋ Remote Control | クラウドのセッションから PC 上の Vault フォルダを直接使う場合（claude.ai の Remote Control でフォルダを共有） |
