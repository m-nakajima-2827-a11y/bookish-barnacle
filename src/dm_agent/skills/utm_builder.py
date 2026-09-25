"""⑤ build_utm_tracking_url"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..utm import build_url, channel_group, check_value

if TYPE_CHECKING:
    from ..runtime import AgentRuntime


def _suggest(value: str) -> str:
    if any(ord(ch) > 127 for ch in value):
        return ""  # dropping Japanese would silently change the meaning → ask for a manual rename
    v = re.sub(r"\s+", "_", value.strip().lower())
    return re.sub(r"[^a-z0-9_\-.]", "", v)


def build_utm_tracking_url(rt: "AgentRuntime", base_url: str, utm_source: str, utm_medium: str, utm_campaign: str,
                           utm_content: str | None = None, utm_term: str | None = None, placement: str | None = None,
                           target_industry: str | None = None) -> dict[str, Any]:
    d = rt.client["utm_dictionary"]
    defaults = d["placement_defaults"].get(placement or "", {})
    if utm_content is None and defaults.get("content"):
        utm_content = defaults["content"] + (f"_{target_industry}" if target_industry and target_industry != "general" else "")
    params = {"utm_source": utm_source, "utm_medium": utm_medium, "utm_campaign": utm_campaign,
              "utm_content": utm_content, "utm_term": utm_term}

    errors = [e for k, v in params.items() if v for e in check_value(k, v)]
    warnings = []
    if utm_source.lower() not in d["sources"]:
        warnings.append(f"utm_source '{utm_source}' は命名辞書にありません（登録済み: {', '.join(d['sources'])}）")
    if utm_medium.lower() not in d["mediums"]:
        warnings.append(f"utm_medium '{utm_medium}' は命名辞書にありません（登録済み: {', '.join(d['mediums'])}）")
    allowed = d["allowed_mediums_by_source"].get(utm_source.lower())
    if defaults.get("medium") and utm_medium.lower() != defaults["medium"]:
        warnings.append(f"設置場所 {placement} には utm_medium='{defaults['medium']}' を推奨します（表記を統一し、集計の分散を防ぐため）")
    elif allowed and utm_medium.lower() not in allowed:
        warnings.append(f"{utm_source} の utm_medium は {allowed} のいずれかに統一してください（'{utm_medium}' は集計が分散します）")
    if defaults.get("source") and utm_source.lower() != defaults["source"]:
        warnings.append(f"設置場所 {placement} には utm_source='{defaults['source']}' を推奨します")
    if not utm_content:
        warnings.append("utm_content が未設定です。プロフィール／ストーリーズ等の設置場所を区別できません")

    url = build_url(base_url, params)
    result = {"status": "invalid" if errors else "ok", "errors": errors, "warnings": warnings,
              "predicted_ga4_channel_group": channel_group(utm_source, utm_medium),
              "params": {k: v for k, v in params.items() if v}}
    if errors:
        fixed = {k: _suggest(v) if v else v for k, v in params.items()}
        blank = [k for k, v in params.items() if v and not fixed[k]]
        if blank:
            result["needs_manual_fix"] = {k: f"'{params[k]}' は自動変換できません。半角英数字で命名してください（例: mfg_paper）"
                                          for k in blank}
        else:
            result["suggested_url"] = build_url(base_url, fixed)
            result["suggested_params"] = {k: v for k, v in fixed.items() if v}
        return result
    result["url"] = url
    if len(url) > 100 and (placement or "").startswith("instagram"):
        result["tip"] = "URLが長いため、プロフィールにはリンク集ツールや短縮URLを使い、遷移先にこのURLを設定してください"
    entry = rt.store.utm_registry.setdefault(utm_campaign, {"campaign": utm_campaign, "industry": target_industry, "urls": []})
    if url not in entry["urls"]:
        entry["urls"].append(url)
    result["registered_campaign"] = utm_campaign
    return result
