from .ads import optimize_ad_and_social_campaigns
from .outreach import trigger_personalized_outreach
from .predict import predict_customer_intent_and_churn
from .report import generate_omnichannel_attribution_report
from .sync import sync_omnichannel_customer_data

HANDLERS = {
    "sync_omnichannel_customer_data": sync_omnichannel_customer_data,
    "predict_customer_intent_and_churn": predict_customer_intent_and_churn,
    "optimize_ad_and_social_campaigns": optimize_ad_and_social_campaigns,
    "trigger_personalized_outreach": trigger_personalized_outreach,
    "generate_omnichannel_attribution_report": generate_omnichannel_attribution_report,
}
