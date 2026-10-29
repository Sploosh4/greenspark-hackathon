"""Current review context. Retained business dates are never shifted."""
from datetime import datetime,timedelta,timezone
from .inputs import load_business
from .public_weather import PERTH
from .current_inputs import business_readiness

def business_coverage(root,now):
    tables,audit=load_business(root)
    result=business_readiness(tables,review_as_of=now.isoformat(),mode='strict')
    for row in result['customers']:
        latest=row['latest_source_usage_date'];row.update(latest_usage_date=latest,required_through=result['required_usage_end'],complete_recent_days=row['recent_eligible_days'],history_status='stale' if latest and latest<result['required_usage_end'] else 'availability_unverified' if latest else 'missing',estimate=None,estimate_reason=row['current_estimate_reason'],account_state_note='Account facts retain their historical source dates; current account status is unverified.')
    result.update(input_files=audit['files'],synthetic_business=True,supplied_usage_end=max((r['latest_source_usage_date'] for r in result['customers'] if r['latest_source_usage_date']),default=None))
    return result
