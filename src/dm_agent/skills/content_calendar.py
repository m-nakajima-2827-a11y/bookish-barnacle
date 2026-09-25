"""⑥ plan_social_content_calendar — BtoB Instagram editorial calendar with measurable CTAs."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from .utm_builder import build_utm_tracking_url

if TYPE_CHECKING:
    from ..runtime import AgentRuntime

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
IND_SHORT = {"it_saas": "it", "manufacturing": "mfg"}
IND_JA = {"it_saas": "IT企業向け", "manufacturing": "製造業向け"}
FALLBACK_PILLARS = ["howto_carousel", "case_study"]


def plan_social_content_calendar(rt: "AgentRuntime", start_date: str, weeks: int, target_industries: list[str],
                                 posting_days: list[str] | None = None, account_status: str = "active",
                                 include_webinar_stories: bool = True) -> dict[str, Any]:
    soc = rt.client["social"]
    lib = {a["asset_id"]: a for a in rt.client["content_library"]}
    days = posting_days or ["mon", "fri"]
    start = date.fromisoformat(start_date)
    start -= timedelta(days=start.weekday())  # align to Monday

    # One profile link per industry (feed posts can't carry clickable links; the CTA points to the profile).
    profile_links = {}
    for ind in target_industries:
        asset = lib[soc["lead_magnet_by_industry"][ind]]
        r = build_utm_tracking_url(rt, asset["url"], "instagram", "social", f"{IND_SHORT[ind]}_paper",
                                   placement="instagram_profile", target_industry=ind)
        profile_links[ind] = {"asset_id": asset["asset_id"], "title": asset["title"], "url": r.get("url")}

    counters: dict[tuple[str, str], int] = {}
    entries, n = [], 0
    for w in range(weeks):
        for d in sorted(days, key=DAYS.index):
            day = start + timedelta(weeks=w, days=DAYS.index(d))
            pillar = soc["weekly_pattern"].get(d) or FALLBACK_PILLARS[n % 2]
            ind = target_industries[n % len(target_industries)]
            themes = soc["themes"][ind][pillar]
            i = counters.get((ind, pillar), 0)
            counters[(ind, pillar)] = i + 1
            spec = soc["pillars"][pillar]
            entries.append({
                "date": day.isoformat(), "weekday": d, "format": spec["format"], "pillar": pillar,
                "target_industry": ind, "theme": themes[i % len(themes)], "goal": spec["goal"], "kpis": spec["kpis"],
                "cta": f"プロフィールのリンクから「{profile_links[ind]['title']}」を無料ダウンロード",
                "link_destination": profile_links[ind]["url"],
                "production_notes": {
                    "howto_carousel": "1枚1テーマの図解。表紙に悩みを言い切る見出し、最終枚に保存を促す一文とCTA",
                    "case_study": "ビフォー→取り組み→アフターの3部構成。数値は顧客の了承を得た実績のみ記載",
                    "expert_reel": "15〜30秒。コンサルタント本人が現場の裏側や考え方を話す",
                }.get(pillar),
            })
            n += 1
        if include_webinar_stories:
            wb = lib[soc["webinar_asset_id"]]
            for ind in target_industries:
                r = build_utm_tracking_url(rt, wb["url"], "instagram", "social", f"webinar_{wb['asset_id'].lower()}",
                                           placement="instagram_story", target_industry=ind)
                entries.append({"date": (start + timedelta(weeks=w, days=2)).isoformat(), "weekday": "wed",
                                "format": "story", "pillar": "webinar_story", "target_industry": ind,
                                "theme": f"{wb['title']}（{IND_JA[ind]}の告知）", "goal": soc["pillars"]["webinar_story"]["goal"],
                                "kpis": soc["pillars"]["webinar_story"]["kpis"], "cta": "リンクスタンプから申込",
                                "link_destination": r.get("url")})
    entries.sort(key=lambda e: (e["date"], e["format"] == "story"))
    out = {"start_date": start.isoformat(), "weeks": weeks, "entries": entries,
           "profile_links": profile_links,
           "monthly_kpis": {"primary": ["保存数", "プロフィールアクセス率（プロフィールアクセス÷リーチ）", "リンククリック数"],
                            "final": ["資料DL数（GA4キーイベント／MA）", "ウェビナー申込数", "DM・フォーム経由の商談獲得数"],
                            "measurement": "GA4で source=instagram の流入とキーイベントを、MAでリード化以降を追跡"},
           "note": "テーマ・構成は下書き案です。投稿文とデザインはブランドトーンに合わせて作成してください。"}
    if account_status == "new":
        out["profile_setup_checklist"] = soc["profile_checklist"]
    return out
