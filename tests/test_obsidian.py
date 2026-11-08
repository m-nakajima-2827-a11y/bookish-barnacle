"""Obsidian 連携: Vault へのノート書き出し・メモ欄の保持・個人情報を書き出さないこと."""

from conftest import at, run_live

from dm_agent.cli import main
from dm_agent.obsidian import END, export_to_obsidian, safe_name

FLOW = ("anon_first_visit", "anon_revisit", "popup_interaction", "form_submit",
        "webinar_attendance", "pricing_visit", "first_contact", "meeting")


def _export(rt, tmp_path, **kw):
    return export_to_obsidian(rt, tmp_path, **kw)


def test_exports_linked_notes(live_rt, scenario, tmp_path):
    run_live(live_rt, scenario, *FLOW)
    res = _export(live_rt, tmp_path)
    root = tmp_path / "DM Agent"
    lead = (root / "リード" / "C00001.md").read_text(encoding="utf-8")
    assert lead.startswith("---\ntype: \"lead\"")
    assert 'stage: "opportunity"' in lead
    assert "[[DM Agent/企業/dom-sample-seiki.example|dom:sample-seiki.example]]" in lead
    assert "[[DM Agent/キャンペーン/mfg_paper]]" in lead
    assert "- [x] 初回接触" in lead  # sales_call 済みなので完了扱い
    account = (root / "企業" / "dom-sample-seiki.example.md").read_text(encoding="utf-8")
    assert "[[DM Agent/リード/C00001]]" in account and "[[DM Agent/リード/L102]]" in account
    assert (root / "00_ダッシュボード.md").exists() and (root / "タスク.md").exists()
    assert res.summary()["written"] == len(list(root.rglob("*.md")))


def test_no_contact_details_written(live_rt, scenario, tmp_path):
    run_live(live_rt, scenario, *FLOW)
    _export(live_rt, tmp_path)
    text = "".join(p.read_text(encoding="utf-8") for p in tmp_path.rglob("*.md"))
    assert "@sample-seiki.example" not in text


def test_reexport_keeps_user_memo_and_is_idempotent(live_rt, scenario, tmp_path):
    run_live(live_rt, scenario, *FLOW)
    _export(live_rt, tmp_path)
    note = tmp_path / "DM Agent" / "リード" / "C00001.md"
    note.write_text(note.read_text(encoding="utf-8") + "決裁者は部長。来期予算で検討。\n", encoding="utf-8")
    at(live_rt, scenario["live"]["lost"]["touchpoints"][-1]["timestamp"])
    live_rt.execute("sync_lead_activity", scenario["live"]["lost"])
    res = _export(live_rt, tmp_path)
    text = note.read_text(encoding="utf-8")
    assert text.split(END, 1)[1].endswith("決裁者は部長。来期予算で検討。\n")
    assert "DM Agent/リード/C00001.md" in res.unchanged or "DM Agent/リード/C00001.md" in res.written
    again = _export(live_rt, tmp_path)
    assert again.written == []


def test_custom_folder_and_funnel_report(live_rt, scenario, tmp_path):
    run_live(live_rt, scenario, *FLOW)
    rep = live_rt.execute("analyze_marketing_funnel", {"period_start": "2026-08-01", "period_end": "2026-09-14",
                                                      "group_by": "source_medium"})
    _export(live_rt, tmp_path, folder="Marketing/BtoB", funnel_reports=[rep])
    report = tmp_path / "Marketing/BtoB" / "レポート" / "ファネル分析 2026-08-01〜2026-09-14.md"
    assert "# マーケティングファネル分析" in report.read_text(encoding="utf-8")
    assert not (tmp_path / "DM Agent").exists()


def test_safe_name():
    assert safe_name("dom:a/b?.example") == "dom-a-b-.example"
    assert safe_name("  ") == "untitled"


def test_cli_obsidian_export_scenario(tmp_path, capsys):
    main(["obsidian-export", "--vault", str(tmp_path), "--scenario",
          "--period-start", "2026-08-01", "--period-end", "2026-09-14"])
    assert '"written"' in capsys.readouterr().out
    assert (tmp_path / "DM Agent" / "00_ダッシュボード.md").exists()
    assert list((tmp_path / "DM Agent" / "レポート").glob("*.md"))
