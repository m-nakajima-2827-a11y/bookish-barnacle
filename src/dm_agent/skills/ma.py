"""In-house MA skills (SATORI の公開されている機能構成をもとにした独自実装)."""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlsplit

from ..ma import engine
from ..ma.email import deliver
from ..ma.popup import decide
from ..ma.store import Profile, mask_email, mask_pii
from ..store import parse_ts

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

FREE_MAIL = {"gmail.com", "yahoo.co.jp", "ymail.ne.jp", "outlook.jp", "outlook.com", "hotmail.com", "hotmail.co.jp",
             "icloud.com", "me.com", "docomo.ne.jp", "ezweb.ne.jp", "softbank.ne.jp", "i.softbank.jp"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LEAD_ACCOUNT_KEYS = ("industry", "employee_band", "job_role", "fiscal_year_end_month")


def _utm_from_url(url: str | None) -> dict[str, str] | None:
    q = dict(parse_qsl(urlsplit(url or "").query))
    utm = {k[4:]: v for k, v in q.items() if k.startswith("utm_")}
    return utm or None


def _profile(rt: "AgentRuntime", customer_id: str | None, visitor_id: str | None) -> Profile | None:
    if customer_id:
        return rt.ma.by_customer(customer_id)
    if visitor_id:
        pid = rt.ma.cookie_index.get(visitor_id)
        return rt.ma.profiles.get(pid) if pid else None
    return None


def _lookup(rt: "AgentRuntime", profile_id: str) -> Profile | None:
    return rt.ma.profiles.get(profile_id) or rt.ma.profiles.get(rt.ma.cookie_index.get(profile_id.removeprefix("anon:"), ""))


# ① 計測 ------------------------------------------------------------------------------------------
def ma_track_activity(rt: "AgentRuntime", events: list[dict[str, Any]], visitor_id: str | None = None,
                      return_popup: bool = True) -> dict[str, Any]:
    ma = rt.ma
    touched: dict[str, Profile] = {}
    results, last_url, last_profile = [], None, None
    for ev in sorted(events, key=lambda e: e["timestamp"]):
        a = {k: v for k, v in ev.items() if k != "email_token"}
        if ev.get("email_token"):
            idx = ma.email_tokens.get(ev["email_token"])
            if idx is None:
                results.append({"type": ev["type"], "status": "ignored", "reason": "unknown email_token"})
                continue
            rec = ma.emails[idx]
            p = _lookup(rt, rec["profile_id"])
            a.update(email_id=rec["email_id"], asset_id=rec.get("asset_id"))
            if ev["type"] == "email_open":
                rec["opens"] += 1
            elif ev["type"] == "email_click":
                rec["clicks"] += 1
                a["url"] = rec.get("link_target")
            elif ev["type"] == "unsubscribe":
                rec["unsubscribed"] = True
        else:
            if not visitor_id:
                results.append({"type": ev["type"], "status": "ignored", "reason": "visitor_id が必要です"})
                continue
            p = engine.profile_for_cookie(rt, visitor_id)
        if p is None:
            continue
        if ev["type"] == "web_access":
            a["utm"] = _utm_from_url(ev.get("url"))
            last_url, last_profile = ev.get("url"), p
        if ev["type"] == "unsubscribe":
            p.unsubscribed, p.email_opt_in = True, False
            ld = rt.store.leads.get(p.customer_id or "")
            if ld:
                ld.unsubscribed, ld.email_opt_in = True, False
        if ev["type"] in {"popup_view", "popup_click"} and ev.get("popup_id") in ma.popups:
            ma.popups[ev["popup_id"]]["stats"]["views" if ev["type"] == "popup_view" else "clicks"] += 1
        if ev["type"] == "push_click":
            for push in ma.pushes:
                if push["push_id"] == ev.get("push_id"):
                    push["clicks"] += 1
        r = engine.record(rt, p, a)
        touched[p.profile_id] = p
        results.append({"type": ev["type"], "points": r["points"], "entered_segments": r["entered_segments"]})
    out = {"events": results, "profiles": [p.public() for p in touched.values()]}
    if return_popup and last_url and last_profile:
        out["popup"] = decide(rt, last_profile, last_url)
    return out


# ② カスタマー ----------------------------------------------------------------------------------
def ma_manage_customer(rt: "AgentRuntime", action: str, customer_id: str | None = None, visitor_id: str | None = None,
                       attributes: dict[str, Any] | None = None, tag: str | None = None,
                       opt_in_evidence: str | None = None, query: dict[str, Any] | None = None) -> dict[str, Any]:
    if action == "search":
        q = query or {}
        hits = [p for p in rt.ma.profiles.values()
                if (not q.get("tag") or q["tag"] in p.tags) and (not q.get("segment_id") or q["segment_id"] in p.segments)
                and p.score >= q.get("min_score", -10**9) and ("identified" not in q or p.identified == q["identified"])]
        hits.sort(key=lambda p: -p.score)
        return {"total": len(hits), "customers": [p.public() for p in hits[: q.get("limit", 50)]]}
    p = _profile(rt, customer_id, visitor_id)
    if p is None:
        return {"error": "customer_not_found"}
    if action == "get":
        return p.public(with_activity=10) | {"score_log": p.score_log[-10:]}
    if action == "update_attributes":
        p.attributes.update({k: v for k, v in (attributes or {}).items() if k not in {"email", "name", "phone"}})
        if p.identified:
            acct = {k: p.attributes[k] for k in LEAD_ACCOUNT_KEYS if k in p.attributes}
            if acct:
                rt.store.ingest(p.customer_id, [], account=acct)
        engine.evaluate_segments(rt, p)
        return {"status": "ok", "customer": p.public()}
    if action in {"add_tag", "remove_tag"}:
        if not tag:
            return {"error": "tag is required"}
        changed = engine.add_tag(rt, p, tag, "manual") if action == "add_tag" else engine.remove_tag(rt, p, tag)
        return {"status": "ok", "changed": changed, "tags": p.tags, "segments": p.segments}
    if action == "unsubscribe":
        p.unsubscribed, p.email_opt_in = True, False
        engine.record(rt, p, {"type": "unsubscribe", "timestamp": rt.now().isoformat(), "source": "manual"})
        if p.identified:
            rt.store.ingest(p.customer_id, [], consent={"email_opt_in": False, "unsubscribed": True})
        return {"status": "ok", "customer": p.public()}
    if action == "record_opt_in":
        if not opt_in_evidence:
            return {"error": "opt_in_evidence is required（同意の取得経路・日時を記録してください）"}
        if p.unsubscribed:
            return {"status": "blocked", "reasons": ["配信停止済みのカスタマーです。本人による再登録が必要です"]}
        p.email_opt_in = True
        p.attributes.setdefault("consent_log", []).append({"at": rt.now().isoformat(), "evidence": opt_in_evidence})
        if p.identified:
            rt.store.ingest(p.customer_id, [], consent={"email_opt_in": True})
        return {"status": "ok", "customer": p.public()}
    return {"error": f"unsupported action {action}"}


# ③ フォーム --------------------------------------------------------------------------------------
def _account_id(email: str, company: str | None) -> str | None:
    domain = email.split("@", 1)[1].lower()
    if domain not in FREE_MAIL:
        return f"dom:{domain}"
    return f"co:{company.strip()}" if company else None


def ma_manage_form(rt: "AgentRuntime", action: str, form_id: str | None = None, definition: dict[str, Any] | None = None,
                   submission: dict[str, Any] | None = None) -> dict[str, Any]:
    ma = rt.ma
    if action == "list":
        return {"forms": [{"form_id": f["form_id"], "name": f["name"], "lead_event": f.get("lead_event"),
                           "submissions": sum(s["form_id"] == f["form_id"] for s in ma.form_submissions)} for f in ma.forms.values()]}
    if action == "create":
        d = dict(definition or {})
        if not d.get("name") or not d.get("fields"):
            return {"error": "definition.name and definition.fields are required"}
        if not any(f.get("type") == "email" for f in d["fields"]):
            return {"error": "メールアドレス項目（type=email）が必要です（名寄せ・実名化のキー）"}
        fid = form_id or ma.next_id("F")
        ma.forms[fid] = {**d, "form_id": fid, "created_at": rt.now().isoformat()}
        return {"status": "created", "form_id": fid,
                "embed": f'<form data-ma-form="{fid}" action="{rt.client["ma"]["tracking_domain"]}/f/{fid}" method="post">…</form>'}
    form = ma.forms.get(form_id or "")
    if form is None:
        return {"error": f"unknown form_id {form_id}"}
    if action == "get":
        return form
    if action != "submit":
        return {"error": f"unsupported action {action}"}

    sub = submission or {}
    values = sub.get("values", {})
    missing = [f["key"] for f in form["fields"] if f.get("required") and not values.get(f["key"])]
    email_key = next(f["key"] for f in form["fields"] if f.get("type") == "email")
    email = (values.get(email_key) or "").strip()
    errors = [f"必須項目が未入力: {k}" for k in missing]
    if email and not EMAIL_RE.match(email):
        errors.append("メールアドレスの形式が正しくありません")
    if errors:
        return {"status": "invalid", "errors": errors}
    ts = sub.get("timestamp") or rt.now().isoformat()

    p = engine.find_by_email(rt, email)
    is_new = p is None
    if is_new:
        p = engine.ensure_customer(rt, ma.next_id("C"))
    contact, attrs = {"email": email}, {}
    for f in form["fields"]:
        v = values.get(f["key"])
        if v in (None, "") or f["key"] == form.get("consent_field"):
            continue
        target = f.get("maps_to", f"attributes.{f['key']}")
        bucket, _, key = target.partition(".")
        (contact if bucket == "contact" else attrs)[key] = v
    engine.set_contact(rt, p, contact)
    p.attributes.update(attrs)
    consent_field = form.get("consent_field")
    consent = bool(consent_field and values.get(consent_field))
    if consent and not p.unsubscribed:
        p.email_opt_in = True
        p.attributes.setdefault("consent_log", []).append({"at": ts, "evidence": f"form:{form['form_id']}"})
    merged = engine.identify(rt, sub.get("visitor_id"), p)

    # リードとして登録（資料DL・セミナー申込・問い合わせ）→ スコアリング・育成・営業引き渡しの自動化へ
    page_url = sub.get("page_url")
    path = urlsplit(page_url or "").path or None
    account = {k: p.attributes[k] for k in LEAD_ACCOUNT_KEYS if k in p.attributes}
    acct_id = _account_id(email, p.attributes.get("company_name"))
    if acct_id:
        account["account_id"] = acct_id
    payload = {k: v for k, v in {"asset_id": form.get("asset_id"), "landing_page": path,
                                  "utm": _utm_from_url(page_url), "form_id": form["form_id"]}.items() if v}
    lead_res = rt.execute("sync_lead_activity", {
        "lead_id": p.customer_id, "account": account,
        "consent": {"email_opt_in": p.email_opt_in, "unsubscribed": p.unsubscribed},
        "touchpoints": [{"channel": "landing_page" if path and path.startswith("/lp/") else "website", "timestamp": ts,
                         "event_type": form.get("lead_event", "contact_request"), "payload": payload}]}, origin="ma_form")

    engine.record(rt, p, {"type": "form_submit", "timestamp": ts, "form_id": form["form_id"], "url": page_url}, forward=False)
    ma.form_submissions.append({"form_id": form["form_id"], "profile_id": p.profile_id, "at": ts, "new_customer": is_new,
                                "merged_anonymous_activities": merged, "page": path})
    for t in form.get("tags_on_submit", []):
        engine.add_tag(rt, p, t, f"form:{form['form_id']}")
    engine.fire_trigger(rt, p, "form_submitted", form["form_id"])
    auto = None
    if form.get("auto_reply"):
        auto = deliver(rt, p, {**form["auto_reply"], "category": "auto_reply", "campaign": f"form_{form['form_id'].lower()}"})
    notes = [engine.notify(rt, p, n, f"フォーム「{form['name']}」送信") for n in form.get("notify", [])]
    ld = rt.store.leads.get(p.customer_id)
    return {"status": "accepted", "customer_id": p.customer_id, "new_customer": is_new, "email": mask_email(email),
            "merged_anonymous_activities": merged, "email_opt_in": p.email_opt_in, "score": p.score, "tags": p.tags,
            "segments": p.segments, "lead_stage": ld.stage if ld else None,
            "auto_reply": auto and {k: auto.get(k) for k in ("status", "reasons", "subject")},
            "notifications": [{k: n.get(k) for k in ("channel", "status")} for n in notes],
            "lead_sync": {k: lead_res.get(k) for k in ("accepted_events", "signals")}}


# ④ LP --------------------------------------------------------------------------------------------
def ma_create_landing_page(rt: "AgentRuntime", slug: str, title: str, headline: str, form_id: str,
                           subheadline: str | None = None, benefits: list[str] | None = None,
                           target_industry: str | None = None, theme_color: str = "#1F3A5F") -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        return {"status": "invalid", "errors": ["slug は半角英小文字・数字・ハイフンのみ（例: mfg-checksheet）"]}
    form = rt.ma.forms.get(form_id)
    if form is None:
        return {"error": f"unknown form_id {form_id}"}
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", theme_color):
        theme_color = "#1F3A5F"
    e = html.escape
    domain = rt.client["ma"]["tracking_domain"]
    fields = []
    for f in form["fields"]:
        req = " required" if f.get("required") else ""
        label = f"<label for=\"{e(f['key'])}\">{e(f['label'])}{'<span>必須</span>' if req else ''}</label>"
        if f["type"] == "select":
            opts = "".join(f"<option value=\"{e(o['value'])}\">{e(o['label'])}</option>" for o in f.get("options", []))
            fields.append(f"{label}<select id=\"{e(f['key'])}\" name=\"{e(f['key'])}\"{req}><option value=\"\">選択してください</option>{opts}</select>")
        elif f["type"] == "checkbox":
            fields.append(f"<label class=\"check\"><input type=\"checkbox\" name=\"{e(f['key'])}\" value=\"1\"{req}> {e(f['label'])}</label>")
        else:
            fields.append(f"{label}<input id=\"{e(f['key'])}\" name=\"{e(f['key'])}\" type=\"{e(f['type'])}\"{req}>")
    items = "".join(f"<li>{e(b)}</li>" for b in (benefits or []))
    sender = rt.client["sender"]
    page = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<style>
:root{{--main:{theme_color}}}body{{margin:0;font-family:"Hiragino Sans","Noto Sans JP",sans-serif;color:#1d2433;background:#f6f7f9}}
header{{background:var(--main);color:#fff;padding:48px 16px;text-align:center}}h1{{margin:0 0 12px;font-size:clamp(22px,4vw,34px)}}
main{{max-width:960px;margin:0 auto;padding:32px 16px;display:grid;gap:32px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}}
ul{{padding-left:1.2em;line-height:1.9}}form{{background:#fff;padding:24px;border-radius:8px;display:grid;gap:8px;box-shadow:0 1px 4px #0001}}
label span{{color:#c0392b;font-size:12px;margin-left:6px}}input,select{{padding:10px;border:1px solid #ccd;border-radius:4px;font-size:16px}}
.check{{font-size:14px}}button{{margin-top:8px;padding:14px;border:0;border-radius:4px;background:var(--main);color:#fff;font-size:16px;font-weight:bold}}
footer{{text-align:center;font-size:12px;color:#667;padding:24px}}
</style>
<!-- MA計測タグ -->
<script async src="{domain}/tag.js" data-ma-page="{e(slug)}"></script>
</head><body>
<header><h1>{e(headline)}</h1>{f"<p>{e(subheadline)}</p>" if subheadline else ""}</header>
<main><section><h2>この資料でわかること</h2><ul>{items}</ul></section>
<form data-ma-form="{e(form_id)}" action="{domain}/f/{e(form_id)}" method="post">{''.join(fields)}
<button type="submit">無料でダウンロード</button></form></main>
<footer>{e(sender['name'])}｜<a href="{rt.client['site_base_url']}/privacy">個人情報の取り扱い</a></footer>
</body></html>"""
    url = f"{rt.client['site_base_url']}/lp/{slug}"
    rt.ma.pages[slug] = {"slug": slug, "url": url, "title": title, "form_id": form_id, "target_industry": target_industry,
                         "created_at": rt.now().isoformat(), "html": page}
    return {"status": "created", "url": url, "form_id": form_id, "html": page,
            "next_steps": ["プライバシーポリシーのURLを確認", "build_utm_tracking_url で流入元ごとのURLを発行",
                           "ポップアップ・広告・Instagramプロフィールのリンク先に設定"]}


# ⑤ セグメント ------------------------------------------------------------------------------------
def ma_manage_segment(rt: "AgentRuntime", action: str, segment_id: str | None = None, name: str | None = None,
                      conditions: dict[str, Any] | None = None, limit: int = 20) -> dict[str, Any]:
    ma = rt.ma

    def members(cond):
        return [p for p in ma.profiles.values() if engine.matches(rt, p, cond)]

    if action == "list":
        return {"segments": [{"segment_id": s["segment_id"], "name": s["name"], "status": s.get("status"),
                              "members": sum(s["segment_id"] in p.segments for p in ma.profiles.values())}
                             for s in ma.segments.values()]}
    if action in {"create", "update", "preview"}:
        cond = conditions or (ma.segments.get(segment_id or "", {}).get("conditions"))
        if not cond:
            return {"error": "conditions is required"}
        try:
            hit = members(cond)
        except (KeyError, ValueError) as ex:
            return {"status": "invalid", "errors": [f"条件の形式が正しくありません: {ex}"]}
        summary = {"members": len(hit), "identified": sum(p.identified for p in hit),
                   "anonymous": sum(not p.identified for p in hit),
                   "sample": [p.public() for p in hit[:limit]]}
        if action == "preview":
            return {"status": "ok", **summary}
        sid = segment_id or ma.next_id("S")
        if action == "update" and sid not in ma.segments:
            return {"error": f"unknown segment_id {sid}"}
        ma.segments[sid] = {**ma.segments.get(sid, {}), "segment_id": sid, "name": name or ma.segments.get(sid, {}).get("name", sid),
                            "conditions": cond, "status": "active"}
        # 作成・更新時点の該当者は所属のみ反映（過去分でシナリオを一斉起動しない）
        ids = {p.profile_id for p in hit}
        for p in ma.profiles.values():
            if p.profile_id in ids and sid not in p.segments:
                p.segments.append(sid)
            elif p.profile_id not in ids and sid in p.segments:
                p.segments.remove(sid)
        return {"status": "created" if action == "create" else "updated", "segment_id": sid, **summary,
                "note": "既存の該当者はシナリオを起動しません。今後新たに該当した人からシナリオが動きます"}
    seg = ma.segments.get(segment_id or "")
    if seg is None:
        return {"error": f"unknown segment_id {segment_id}"}
    if action == "pause":
        seg["status"] = "paused"
        return {"status": "paused", "segment_id": segment_id}
    if action == "members":
        ms = [p for p in ma.profiles.values() if segment_id in p.segments]
        return {"segment_id": segment_id, "total": len(ms), "members": [p.public() for p in ms[:limit]]}
    return {"error": f"unsupported action {action}"}


# ⑥ スコア定義 ------------------------------------------------------------------------------------
def ma_configure_scoring(rt: "AgentRuntime", action: str, action_type: str | None = None, points: int | None = None,
                         rule: dict[str, Any] | None = None, rule_id: str | None = None) -> dict[str, Any]:
    sd = rt.ma.score_definition
    if action == "get":
        return {"common": {**engine.DEFAULT_COMMON_SCORES, **sd["common"]}, "individual": sd["individual"],
                "note": "個別設定に該当したWebアクセスは個別設定の点数を適用し、共通設定は加算しません"}
    if action == "set_common":
        if action_type is None or points is None:
            return {"error": "action_type and points are required"}
        sd["common"][action_type] = points
        return {"status": "ok", "common": {**engine.DEFAULT_COMMON_SCORES, **sd["common"]},
                "note": "変更は今後のアクションから適用されます（過去分は再計算しません）"}
    if action == "add_rule":
        r = dict(rule or {})
        if r.get("target") not in {"web_access", "form_submit", "tag_added", "segment_entered"} or not isinstance(r.get("points"), int):
            return {"error": "rule.target (web_access|form_submit|tag_added|segment_entered) and integer rule.points are required"}
        if abs(r["points"]) > engine.SCORE_LIMIT:
            return {"error": "points は±100,000以内の整数です"}
        if r["target"] == "web_access" and not (r.get("url_filter") or r.get("param_filter")):
            return {"error": "web_access の個別設定には url_filter または param_filter が必要です"}
        r["rule_id"] = rt.ma.next_id("R")
        sd["individual"].append(r)
        return {"status": "ok", "rule": r}
    if action == "remove_rule":
        before = len(sd["individual"])
        sd["individual"] = [r for r in sd["individual"] if r.get("rule_id") != rule_id]
        return {"status": "ok" if len(sd["individual"]) < before else "not_found", "rule_id": rule_id}
    if action == "distribution":
        idf = [p.score for p in rt.ma.profiles.values() if p.identified]
        anon = [p.score for p in rt.ma.profiles.values() if not p.identified]
        bands = [(-10**9, 0), (0, 20), (20, 50), (50, 100), (100, 10**9)]
        lab = lambda lo, hi: f"{lo}〜{hi - 1}" if hi < 10**9 and lo > -10**9 else (f"{hi - 1}以下" if lo == -10**9 else f"{lo}以上")
        return {"bands": [{"band": lab(lo, hi), "identified": sum(lo <= s < hi for s in idf),
                           "anonymous": sum(lo <= s < hi for s in anon)} for lo, hi in bands]}
    return {"error": f"unsupported action {action}"}


# ⑦ シナリオ --------------------------------------------------------------------------------------
STEP_ACTIONS = {"send_email", "add_tag", "remove_tag", "notify"}


def ma_manage_scenario(rt: "AgentRuntime", action: str, scenario_id: str | None = None,
                       definition: dict[str, Any] | None = None, customer_id: str | None = None) -> dict[str, Any]:
    ma = rt.ma

    def stats(sid):
        c = Counter(e["status"] for e in ma.enrollments.values() if e["scenario_id"] == sid)
        return {"active": c["active"], "completed": c["completed"], "exited": c["exited"]}

    if action == "list":
        return {"scenarios": [{"scenario_id": s["scenario_id"], "name": s["name"], "status": s["status"],
                               "trigger": s["trigger"], "steps": len(s["steps"]), **stats(s["scenario_id"])}
                              for s in ma.scenarios.values()]}
    if action == "create":
        d = dict(definition or {})
        errs = []
        trg = d.get("trigger") or {}
        if trg.get("type") not in {"segment_entered", "form_submitted", "tag_added", "manual"}:
            errs.append("trigger.type は segment_entered / form_submitted / tag_added / manual")
        if trg.get("type") == "segment_entered" and trg.get("key") not in ma.segments:
            errs.append(f"trigger.key のセグメント {trg.get('key')} が存在しません")
        if trg.get("type") == "form_submitted" and trg.get("key") not in ma.forms:
            errs.append(f"trigger.key のフォーム {trg.get('key')} が存在しません")
        for i, st in enumerate(d.get("steps") or []):
            if st.get("action") not in STEP_ACTIONS:
                errs.append(f"steps[{i}].action が不正です")
            if st.get("action") == "send_email" and not (st.get("email") or {}).get("subject"):
                errs.append(f"steps[{i}].email.subject が必要です")
        if not d.get("steps"):
            errs.append("steps が必要です")
        if errs:
            return {"status": "invalid", "errors": errs}
        sid = scenario_id or ma.next_id("SC")
        ma.scenarios[sid] = {**d, "scenario_id": sid, "status": "draft"}
        return {"status": "created", "scenario_id": sid, "scenario_status": "draft",
                "note": "action=activate で開始します。開始前に件名・本文・配信日数を確認してください"}
    sc = ma.scenarios.get(scenario_id or "")
    if sc is None:
        return {"error": f"unknown scenario_id {scenario_id}"}
    if action in {"activate", "pause"}:
        sc["status"] = "active" if action == "activate" else "paused"
        return {"status": sc["status"], "scenario_id": scenario_id}
    if action == "get":
        return {**sc, **stats(scenario_id)}
    if action == "enroll":
        p = ma.by_customer(customer_id or "")
        if p is None:
            return {"error": "customer_not_found"}
        if sc["status"] != "active":
            return {"status": "blocked", "reasons": ["シナリオが開始されていません"]}
        return engine.enroll(rt, scenario_id, p, source="manual")
    return {"error": f"unsupported action {action}"}


# ⑧ メール配信 ------------------------------------------------------------------------------------
def ma_send_email(rt: "AgentRuntime", subject: str, customer_id: str | None = None, segment_id: str | None = None,
                  body: str | None = None, asset_id: str | None = None, link_url: str | None = None,
                  campaign: str | None = None, schedule_at: str | None = None, test_only: bool = False) -> dict[str, Any]:
    ma = rt.ma
    if bool(customer_id) == bool(segment_id):
        return {"error": "customer_id か segment_id のどちらか一方を指定してください"}
    if asset_id and not any(a["asset_id"] == asset_id for a in rt.client["content_library"]):
        return {"error": f"unknown asset_id {asset_id}"}
    if customer_id:
        p = ma.by_customer(customer_id)
        targets = [p] if p else []
    else:
        if segment_id not in ma.segments:
            return {"error": f"unknown segment_id {segment_id}"}
        targets = [p for p in ma.profiles.values() if segment_id in p.segments]
    targets = [p for p in targets if p and p.identified]
    spec = {"subject": subject, "body": body, "asset_id": asset_id, "link_url": link_url, "campaign": campaign,
            "category": "bulk" if segment_id else "single"}
    if test_only:
        ok = [p for p in targets if p.contact.get("email") and p.email_opt_in and not p.unsubscribed]
        return {"status": "test", "targets": len(targets), "deliverable_estimate": len(ok),
                "excluded": {"no_opt_in_or_unsubscribed": len(targets) - len(ok)}, "subject": subject}
    if schedule_at:
        at = parse_ts(schedule_at)
        if at <= rt.now():
            return {"error": "schedule_at は未来の日時を指定してください"}
        rt.schedule(at, "_ma_bulk_send", {"args": {k: v for k, v in {"subject": subject, "customer_id": customer_id,
                                                                      "segment_id": segment_id, "body": body, "asset_id": asset_id,
                                                                      "link_url": link_url, "campaign": campaign}.items() if v}})
        return {"status": "scheduled", "scheduled_at": at.isoformat(), "targets_now": len(targets)}
    results = [deliver(rt, p, spec) for p in targets]
    c = Counter(r["status"] for r in results)
    reasons = Counter(x.split(":")[0] for r in results for x in r.get("reasons", []))
    return {"status": "done", "targets": len(targets), "result": dict(c), "blocked_reasons": dict(reasons),
            "sample": [mask_pii({k: r.get(k) for k in ("customer_id", "status", "to", "scheduled_at")}) for r in results[:5]]}


# ⑨ ポップアップ ----------------------------------------------------------------------------------
def ma_manage_popup(rt: "AgentRuntime", action: str, popup_id: str | None = None, definition: dict[str, Any] | None = None,
                    visitor_id: str | None = None, url: str | None = None) -> dict[str, Any]:
    ma = rt.ma
    if action == "list":
        return {"popups": [{"popup_id": p["popup_id"], "name": p["name"], "status": p["status"], **p["stats"],
                            "ctr": round(p["stats"]["clicks"] / p["stats"]["views"], 3) if p["stats"]["views"] else None}
                           for p in ma.popups.values()]}
    if action == "create":
        d = dict(definition or {})
        if d.get("type") not in {"form", "banner"} or not d.get("content"):
            return {"error": "definition.type (form|banner) and definition.content are required"}
        if d["type"] == "form" and d["content"].get("form_id") not in ma.forms:
            return {"error": "form 型には存在する content.form_id が必要です"}
        if d.get("conditions", {}).get("segment_id") and d["conditions"]["segment_id"] not in ma.segments:
            return {"error": "conditions.segment_id が存在しません"}
        pid = popup_id or ma.next_id("P")
        ma.popups[pid] = {**d, "popup_id": pid, "conditions": d.get("conditions", {}), "status": "active",
                          "stats": {"views": 0, "clicks": 0}}
        return {"status": "created", "popup_id": pid}
    if action == "decide":
        if not visitor_id or not url:
            return {"error": "visitor_id and url are required"}
        return {"popup": decide(rt, engine.profile_for_cookie(rt, visitor_id), url)}
    pop = ma.popups.get(popup_id or "")
    if pop is None:
        return {"error": f"unknown popup_id {popup_id}"}
    pop["status"] = "paused" if action == "pause" else "active"
    return {"status": pop["status"], "popup_id": popup_id}


# ⑩ Webプッシュ -----------------------------------------------------------------------------------
def ma_send_web_push(rt: "AgentRuntime", title: str, url: str, body: str | None = None, segment_id: str | None = None,
                     schedule_at: str | None = None, test_only: bool = False) -> dict[str, Any]:
    ma, g, now = rt.ma, rt.guardrails, rt.now()
    if segment_id and segment_id not in ma.segments:
        return {"error": f"unknown segment_id {segment_id}"}
    targets = [p for p in ma.profiles.values() if p.push_subscribed and (not segment_id or segment_id in p.segments)]
    cap = rt.policy.get("push", {}).get("frequency_cap_per_7days", 3)
    recent = lambda p: sum(1 for x in ma.pushes if x["status"] == "sent" and p.profile_id in x["recipients"]
                           and now - parse_ts(x["sent_at"]) < timedelta(days=7))
    eligible = [p for p in targets if recent(p) < cap]
    if test_only:
        return {"status": "test", "subscribed_targets": len(targets), "eligible": len(eligible), "frequency_cap": cap}
    at = parse_ts(schedule_at) if schedule_at else now
    if at <= now and not g.in_business_hours(now):
        at = g.next_business_open(now)
    if at > now:
        rt.schedule(at, "_ma_push", {"args": {k: v for k, v in {"title": title, "url": url, "body": body,
                                                                "segment_id": segment_id}.items() if v}})
        return {"status": "scheduled", "scheduled_at": at.isoformat(), "targets_now": len(eligible)}
    push_id = ma.next_id("W")
    rec = {"push_id": push_id, "title": title, "url": url, "segment_id": segment_id, "sent_at": now.isoformat(),
           "recipients": [p.profile_id for p in eligible], "clicks": 0,
           "skipped_frequency_cap": len(targets) - len(eligible)}
    if g.dry_run:
        rec["status"] = "planned"
    else:
        for p in eligible:
            rt.push.send(p.profile_id, {"title": title, "body": body, "url": url, "push_id": push_id})
        rec["status"] = "sent"
    ma.pushes.append(rec)
    return {k: v for k, v in rec.items() if k != "recipients"} | {"recipients": len(rec["recipients"])}


# ⑪ レポート --------------------------------------------------------------------------------------
def ma_get_report(rt: "AgentRuntime", report_type: str, period_start: str | None = None,
                  period_end: str | None = None) -> dict[str, Any]:
    ma, tz = rt.ma, rt.guardrails.tz
    lo = datetime.combine(date.fromisoformat(period_start), time.min, tz) if period_start else None
    hi = datetime.combine(date.fromisoformat(period_end), time.min, tz) + timedelta(days=1) if period_end else None
    inp = lambda ts: ts and (lo is None or parse_ts(ts) >= lo) and (hi is None or parse_ts(ts) < hi)
    rate = lambda a, b: round(a / b, 3) if b else None
    if report_type == "overview":
        ps = list(ma.profiles.values())
        idf = [p for p in ps if p.identified]
        subs = [s for s in ma.form_submissions if inp(s["at"])]
        return {"customers": len(ps), "identified": len(idf), "anonymous": len(ps) - len(idf),
                "identified_rate": rate(len(idf), len(ps)), "email_opt_in": sum(p.email_opt_in and not p.unsubscribed for p in idf),
                "push_subscribed": sum(p.push_subscribed for p in ps), "form_submissions": len(subs),
                "new_identified_by_form": sum(s["new_customer"] for s in subs),
                "anonymous_history_merged": sum(s["merged_anonymous_activities"] for s in subs),
                "score_distribution": ma_configure_scoring(rt, "distribution")["bands"]}
    if report_type == "email":
        rows: dict[str, dict[str, Any]] = {}
        for r in ma.emails:
            if not inp(r.get("sent_at") or r.get("at")):
                continue
            key = r.get("scenario_id") or r["category"]
            x = rows.setdefault(key, {"group": key, "sent": 0, "planned": 0, "blocked": 0, "opened": 0, "clicked": 0, "unsubscribed": 0})
            x[r["status"]] = x.get(r["status"], 0) + 1
            x["opened"] += bool(r.get("opens"))
            x["clicked"] += bool(r.get("clicks"))
            x["unsubscribed"] += bool(r.get("unsubscribed"))
        for x in rows.values():
            x.update(open_rate=rate(x["opened"], x["sent"]), click_rate=rate(x["clicked"], x["sent"]),
                     unsubscribe_rate=rate(x["unsubscribed"], x["sent"]))
        return {"rows": list(rows.values()),
                "note": "開封率は画像表示に依存するため参考値です（画像非表示の環境では計測されません）"}
    if report_type == "popup":
        return ma_manage_popup(rt, "list")
    if report_type == "form":
        out = []
        for f in ma.forms.values():
            subs = [s for s in ma.form_submissions if s["form_id"] == f["form_id"] and inp(s["at"])]
            out.append({"form_id": f["form_id"], "name": f["name"], "submissions": len(subs),
                        "new_customers": sum(s["new_customer"] for s in subs),
                        "with_anonymous_history": sum(s["merged_anonymous_activities"] > 0 for s in subs)})
        return {"forms": out}
    if report_type == "push":
        return {"pushes": [{k: v for k, v in x.items() if k != "recipients"} | {"recipients": len(x["recipients"]),
                           "ctr": rate(x["clicks"], len(x["recipients"]))} for x in ma.pushes if inp(x["sent_at"])]}
    if report_type == "scenario":
        return ma_manage_scenario(rt, "list")
    if report_type == "segment":
        return ma_manage_segment(rt, "list")
    return {"error": f"unsupported report_type {report_type}"}
