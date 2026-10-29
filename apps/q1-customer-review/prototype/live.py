"""Current review context. Retained business dates are never shifted."""
from datetime import datetime,timedelta,timezone
from .inputs import load_business
from .public_weather import PERTH

def business_coverage(root,now):
    tables,audit=load_business(root);cutoff=(now.astimezone(PERTH).date()-timedelta(days=1)).isoformat()
    dates={r['customer_id']:{} for r in tables['customers']}
    for r in tables['consumption_daily']:
        if r['date']<=cutoff:dates[r['customer_id']][r['date']]=r
    customers=[];first=(datetime.fromisoformat(cutoff).date()-timedelta(days=6))
    for c in tables['customers']:
        records=dates[c['customer_id']];recent=[records.get((first+timedelta(days=i)).isoformat()) for i in range(7)]
        latest=max(records,default=None);complete=all(r and r['supply_status']=='connected' and float(r['outage_hours'])==0 for r in recent)
        customers.append({'customer_id':c['customer_id'],'latest_usage_date':latest,'required_through':cutoff,'complete_recent_days':sum(bool(r and r['supply_status']=='connected' and float(r['outage_hours'])==0) for r in recent),'history_status':'complete' if complete else 'stale' if latest and latest<cutoff else 'missing','estimate':None,'estimate_reason':'weather_classification_unavailable' if complete else 'current_usage_history_unavailable','account_state_note':'Account facts retain their historical source dates; current account status is unverified.'})
    return {'customers':customers,'required_usage_start':first.isoformat(),'required_usage_end':cutoff,'input_files':audit['files'],'synthetic_business':True,'date_shifting':False}
