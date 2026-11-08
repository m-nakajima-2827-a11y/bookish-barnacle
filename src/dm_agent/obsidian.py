"""Obsidian 連携: エージェントの状態を Obsidian の Vault に Markdown ノートとして書き出す.

Obsidian の Vault は Markdown ファイルのフォルダなので、API を介さずファイルを書き出して連携します。

- ノートは Vault 内の専用フォルダ（既定 ``DM Agent/``）にだけ書き込みます。
- 各ノートは YAML フロントマター（Obsidian のプロパティ）と ``[[wikilink]]`` で
  リード ⇔ 企業 ⇔ キャンペーン ⇔ レポートを相互リンクします。
- エージェントが生成する部分は ``<!-- dm-agent:begin -->``〜``<!-- dm-agent:end -->`` の間だけです。
  終了マーカーより後ろ（「メモ」欄）は再エクスポートしても保持されるので、営業メモを追記できます。
- 連絡先（氏名・メールアドレス・電話番号）は書き出しません。リードはIDと企業属性のみです。
- CRMタスクは Obsidian Tasks プラグインの書式（``- [ ] ... 📅 YYYY-MM-DD``）で出力します。
  プラグインがなくても通常のチェックリストとして読めます。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runtime import AgentRuntime

BEGIN = "<!-- dm-agent:begin -->"
END = "<!-- dm-agent:end -->"
DEFAULT_FOLDER = "DM Agent"
MEMO = "\n\n## メモ\n\n"

STAGE_LABELS = {"lead": "リード", "mql": "MQL", "hot": "ホットリード", "sql": "SQL（営業引き渡し済み）",
                "opportunity": "商談", "customer": "受注", "recycled": "再育成（失注・保留）", "disqualified": "対象外"}
TASK_LABELS = {"first_contact": "初回接触", "recontact": "再アプローチ", "ma_alert": "MA通知"}
PRIORITY_ICONS = {"high": " ⏫", "normal": ""}


def safe_name(value: str) -> str:
    """Obsidian・Windows・macOS で使えないファイル名の文字を置き換える."""
    name = re.sub(r'[\\/:*?"<>|#^\[\]]', "-", str(value)).strip(" .")
    return name or "untitled"


def link(folder: str, name: str, label: str | None = None) -> str:
    target = f"{folder}/{safe_name(name)}"
    shown = label if label is not None else str(name)
    return f"[[{target}]]" if shown == safe_name(name) else f"[[{target}|{shown}]]"


def _yaml_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        if not v:
            return "[]"
        return "\n" + "\n".join(f"  - {json.dumps(str(x), ensure_ascii=False)}" for x in v)
    return json.dumps(str(v), ensure_ascii=False)  # JSON 文字列は YAML として有効


def frontmatter(props: dict[str, Any]) -> str:
    lines = [f"{k}: {_yaml_value(v)}".rstrip() for k, v in props.items()]
    return "---\n" + "\n".join(lines) + "\n---\n"


def _date(ts: str | None) -> str | None:
    return ts[:10] if ts else None


@dataclass
class ExportResult:
    vault: Path
    folder: str
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {"vault": str(self.vault), "folder": self.folder, "written": len(self.written),
                "unchanged": len(self.unchanged), "index": f"{self.folder}/00_ダッシュボード.md"}


class ObsidianVault:
    """Vault 内の専用フォルダへのノート書き込み（ユーザーのメモ欄を保持）."""

    def __init__(self, vault: Path | str, folder: str = DEFAULT_FOLDER):
        self.vault = Path(vault).expanduser()
        self.folder = folder.strip("/") or DEFAULT_FOLDER
        self.root = self.vault / self.folder
        self.result = ExportResult(self.vault, self.folder)

    def write(self, rel: str, props: dict[str, Any], body: str) -> Path:
        path = self.root / rel
        managed = f"{BEGIN}\n{body.rstrip()}\n{END}"
        memo = MEMO
        if path.exists():
            old = path.read_text(encoding="utf-8")
            if END in old:
                memo = old.split(END, 1)[1]
        content = frontmatter({**props, "generated_by": "dm-agent"}) + "\n" + managed + memo
        if not content.endswith("\n"):
            content += "\n"
        rel_out = f"{self.folder}/{rel}"
        if path.exists() and path.read_text(encoding="utf-8") == content:
            self.result.unchanged.append(rel_out)
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.result.written.append(rel_out)
        return path


def _lead_note(rt: "AgentRuntime", ld, tasks: list[dict[str, Any]], titles: dict[str, str], f: str) -> tuple[dict, str]:
    score = ld.score or {}
    ft, lt = ld.first_touch or {}, ld.last_touch or {}
    props = {
        "type": "lead", "lead_id": ld.lead_id, "stage": ld.stage, "account": link(f + "/企業", ld.account_id) if ld.account_id else None,
        "industry": ld.industry, "employee_band": ld.employee_band, "job_role": ld.job_role,
        "fit": score.get("fit"), "engagement": score.get("engagement"), "grade": score.get("grade"),
        "first_touch_campaign": ft.get("campaign"), "first_seen": _date(ld.first_seen), "last_seen": _date(ld.last_seen),
        "email_opt_in": ld.email_opt_in and not ld.unsubscribed,
        "tags": ["dm-agent/lead", f"stage/{ld.stage}"] + ([f"industry/{ld.industry}"] if ld.industry else []),
    }
    L = [f"# リード {ld.lead_id}", "",
         f"- ステージ: **{STAGE_LABELS.get(ld.stage, ld.stage)}**",
         f"- 企業: {link(f + '/企業', ld.account_id) if ld.account_id else '未特定'}",
         f"- 属性: {ld.industry or '-'} / {ld.employee_band or '-'} / {ld.job_role or '-'}"]
    if score:
        L.append(f"- スコア: フィット {score.get('fit')} × エンゲージメント {score.get('engagement')}（{score.get('grade', '-')}）")
    if ft:
        camp = link(f + "/キャンペーン", ft["campaign"]) if ft.get("campaign") else "-"
        L.append(f"- 初回接点: {_date(ft.get('timestamp'))} {ft.get('source') or '-'} / {ft.get('medium') or '-'} / {camp}")
    if lt and lt != ft:
        where = " / ".join(x for x in (lt.get("source"), lt.get("medium"), lt.get("landing_page")) if x)
        L.append(f"- 最終接点: {_date(lt.get('timestamp'))} {where or '-'}")
    if ld.consumed_assets:
        L += ["", "## 閲覧・取得したコンテンツ", ""] + [f"- {titles.get(a, a)}（{a}）" for a in ld.consumed_assets]
    if ld.handoff:
        h = ld.handoff
        L += ["", "## 営業引き渡し", "", f"- 引き渡し: {h.get('at', '')[:16]} / 期限: {h.get('due_at', '')[:16]}",
              f"- 初回接触: {h.get('first_contact_at', '未接触')[:16]}"]
    if ld.opportunity:
        o = ld.opportunity
        L += ["", "## 商談", "", f"- 状態: {o.get('status')} / 金額: {o.get('amount', 0):,.0f}円 / 作成: {_date(o.get('created_at'))}"]
    if ld.lost_reason:
        L.append(f"- 失注理由: {ld.lost_reason}")
    if tasks:
        L += ["", "## タスク", ""] + [_task_line(t, f) for t in tasks]
    if ld.stage_history:
        L += ["", "## ステージ履歴", "", "| 日時 | 変更 | 理由 |", "|---|---|---|"]
        L += [f"| {h['at'][:16]} | {h['from']} → {h['to']} | {h['reason']} |" for h in ld.stage_history]
    events = rt.store.events.get(ld.lead_id, [])
    if events:
        L += ["", "## 行動履歴（直近20件）", "", "| 日時 | チャネル | 行動 | 詳細 |", "|---|---|---|---|"]
        for e in events[-20:]:
            p = e.get("payload") or {}
            detail = p.get("asset_id") or p.get("landing_page") or (p.get("utm") or {}).get("campaign") or ""
            L.append(f"| {e['timestamp'][:16]} | {e['channel']} | {e['event_type']} | {detail} |")
    return props, "\n".join(L)


def _task_line(t: dict[str, Any], f: str) -> str:
    done = "x" if t.get("status") == "done" else " "
    label = TASK_LABELS.get(t.get("type"), t.get("type", "タスク"))
    who = link(f + "/リード", t["lead_id"]) if t.get("lead_id") else ""
    ctx = t.get("context") or {}
    extra = ctx.get("lost_reason") and f"（失注理由: {ctx['lost_reason']}）" or ""
    due = f" 📅 {_date(t.get('due_at'))}" if t.get("due_at") else ""
    return f"- [{done}] {label}: {who}{extra}{due}{PRIORITY_ICONS.get(t.get('priority'), '')}"


def export_to_obsidian(rt: "AgentRuntime", vault: Path | str, folder: str = DEFAULT_FOLDER,
                       funnel_reports: list[dict[str, Any]] | None = None,
                       extra_notes: dict[str, str] | None = None) -> ExportResult:
    """リード・企業・キャンペーン・タスク・レポートを Obsidian ノートとして書き出す.

    funnel_reports: ``analyze_marketing_funnel`` の結果（``markdown`` を含む dict）のリスト。
    extra_notes: ``{"レポート/xxx.md": "markdown"}`` 形式の追加ノート。
    """
    v = ObsidianVault(vault, folder)
    f = v.folder
    client_name = rt.client.get("name", "")
    titles = {a["asset_id"]: a.get("title", a["asset_id"]) for a in rt.client.get("content_library", [])}
    tasks_by_lead: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in getattr(rt.crm, "tasks", []):
        ld = rt.store.leads.get(t.get("lead_id") or "")
        if t.get("type") == "first_contact" and ld and (ld.handoff or {}).get("first_contact_at"):
            t = {**t, "status": "done"}  # 初回接触済み（行動履歴の sales_call で判定）
        tasks_by_lead[t.get("lead_id") or ""].append(t)

    leads = sorted(rt.store.leads.values(), key=lambda l: l.lead_id)
    accounts: dict[str, list] = defaultdict(list)
    campaigns: dict[str, list] = defaultdict(list)
    for ld in leads:
        props, body = _lead_note(rt, ld, tasks_by_lead.get(ld.lead_id, []), titles, f)
        v.write(f"リード/{safe_name(ld.lead_id)}.md", props, body)
        if ld.account_id:
            accounts[ld.account_id].append(ld)
        if ld.first_touch and ld.first_touch.get("campaign"):
            campaigns[ld.first_touch["campaign"]].append(ld)

    for acc, members in sorted(accounts.items()):
        industry = next((m.industry for m in members if m.industry), None)
        pipeline = sum((m.opportunity or {}).get("amount", 0) for m in members if (m.opportunity or {}).get("status") != "lost")
        props = {"type": "account", "account_id": acc, "industry": industry, "contacts": len(members),
                 "pipeline_amount": pipeline, "tags": ["dm-agent/account"]}
        L = [f"# 企業 {acc}", "", f"- 業界: {industry or '-'} / 関与している担当者: {len(members)}名",
             f"- 商談金額（進行中・受注）: {pipeline:,.0f}円", "", "## 担当者（購買関与者）", "",
             "| リード | ステージ | 役職 | スコア |", "|---|---|---|---|"]
        L += [f"| {link(f + '/リード', m.lead_id)} | {m.stage} | {m.job_role or '-'} | "
              f"{(m.score or {}).get('grade', '-')} |" for m in members]
        if len(members) >= 2:
            L += ["", "> [!tip] 同一企業の複数担当者が関与しています（購買委員会の可能性・仮説）。"]
        v.write(f"企業/{safe_name(acc)}.md", props, "\n".join(L))

    for camp in sorted(set(campaigns) | set(rt.store.utm_registry)):
        reg = rt.store.utm_registry.get(camp, {})
        members = campaigns.get(camp, [])
        props = {"type": "campaign", "utm_campaign": camp, "industry": reg.get("industry"),
                 "first_touch_leads": len(members), "tags": ["dm-agent/campaign"]}
        L = [f"# キャンペーン {camp}", "", f"- 対象業界: {reg.get('industry') or '-'}",
             f"- 初回接点がこのキャンペーンのリード: {len(members)}件"]
        if reg.get("urls"):
            L += ["", "## 計測用URL（UTM）", ""] + [f"- `{u}`" for u in reg["urls"]]
        if members:
            L += ["", "## リード", ""] + [f"- {link(f + '/リード', m.lead_id)}（{m.stage}）" for m in members]
        v.write(f"キャンペーン/{safe_name(camp)}.md", props, "\n".join(L))

    report_links = []
    for rep in funnel_reports or []:
        if not rep.get("markdown"):
            continue
        p = rep.get("period", {})
        name = f"ファネル分析 {p.get('start', '')}〜{p.get('end', '')}"
        props = {"type": "report", "report": "funnel", "period_start": p.get("start"), "period_end": p.get("end"),
                 "group_by": rep.get("group_by"), "tags": ["dm-agent/report"]}
        v.write(f"レポート/{safe_name(name)}.md", props, rep["markdown"])
        report_links.append(link(f + "/レポート", name))
    for rel, md in (extra_notes or {}).items():
        v.write(rel, {"type": "report", "tags": ["dm-agent/report"]}, md)
        report_links.append(f"[[{f}/{rel.removesuffix('.md')}]]")

    all_tasks = [t for ts in tasks_by_lead.values() for t in ts]
    all_tasks.sort(key=lambda t: t.get("due_at") or "")
    v.write("タスク.md", {"type": "tasks", "tags": ["dm-agent/tasks"]},
            "\n".join(["# 営業・MAタスク", "", "CRMに登録されたタスクです（Obsidian Tasks プラグインの書式）。", ""]
                      + ([_task_line(t, f) for t in all_tasks] or ["- タスクはありません"])))

    stage_count = defaultdict(int)
    for ld in leads:
        stage_count[ld.stage] += 1
    hot = [ld for ld in leads if ld.stage in {"hot", "sql"}]
    L = [f"# {client_name} マーケティング ダッシュボード", "",
         f"最終エクスポート: {rt.now().isoformat(timespec='minutes')}", "", "## ステージ別リード数", "",
         "| ステージ | 件数 |", "|---|---:|"]
    L += [f"| {STAGE_LABELS.get(s, s)} | {stage_count[s]} |" for s in STAGE_LABELS if stage_count.get(s)]
    L += ["", "## 優先対応（ホットリード・SQL）", ""]
    L += [f"- {link(f + '/リード', ld.lead_id)} {ld.industry or ''} {ld.job_role or ''}（{ld.stage}）" for ld in hot] or ["- 該当なし"]
    L += ["", "## 一覧", "", f"- [[{f}/タスク|タスク]]",
          f"- 企業: " + (", ".join(link(f + "/企業", a) for a in sorted(accounts)) or "-"),
          f"- キャンペーン: " + (", ".join(link(f + "/キャンペーン", c) for c in sorted(set(campaigns) | set(rt.store.utm_registry))) or "-")]
    if report_links:
        L += ["- レポート: " + ", ".join(report_links)]
    L += ["", "## Dataview（プラグイン導入時のみ表示）", "", "```dataview",
          "TABLE stage, industry, job_role, grade, last_seen", f'FROM "{f}/リード"',
          'WHERE stage = "hot" OR stage = "sql" OR stage = "mql"', "SORT last_seen DESC", "```"]
    v.write("00_ダッシュボード.md", {"type": "dashboard", "client": client_name, "tags": ["dm-agent"]}, "\n".join(L))
    return v.result
