from .ads import optimize_lead_gen_campaigns
from .content_calendar import plan_social_content_calendar
from .funnel import analyze_marketing_funnel
from .nurture import trigger_nurture_action
from .scoring import score_and_qualify_leads
from .sync import sync_lead_activity
from .utm_builder import build_utm_tracking_url

HANDLERS = {
    "sync_lead_activity": sync_lead_activity,
    "score_and_qualify_leads": score_and_qualify_leads,
    "trigger_nurture_action": trigger_nurture_action,
    "optimize_lead_gen_campaigns": optimize_lead_gen_campaigns,
    "build_utm_tracking_url": build_utm_tracking_url,
    "plan_social_content_calendar": plan_social_content_calendar,
    "analyze_marketing_funnel": analyze_marketing_funnel,
}
