from .ads import optimize_lead_gen_campaigns
from .content_calendar import plan_social_content_calendar
from .funnel import analyze_marketing_funnel
from .ma import (ma_configure_scoring, ma_create_landing_page, ma_get_report, ma_manage_customer, ma_manage_form,
                 ma_manage_popup, ma_manage_scenario, ma_manage_segment, ma_send_email, ma_send_web_push,
                 ma_track_activity)
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
    "ma_track_activity": ma_track_activity,
    "ma_manage_customer": ma_manage_customer,
    "ma_manage_form": ma_manage_form,
    "ma_create_landing_page": ma_create_landing_page,
    "ma_manage_segment": ma_manage_segment,
    "ma_configure_scoring": ma_configure_scoring,
    "ma_manage_scenario": ma_manage_scenario,
    "ma_send_email": ma_send_email,
    "ma_manage_popup": ma_manage_popup,
    "ma_send_web_push": ma_send_web_push,
    "ma_get_report": ma_get_report,
}
