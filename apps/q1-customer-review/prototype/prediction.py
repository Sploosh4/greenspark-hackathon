"""Replaceable prediction boundary. This baseline makes no causal/accuracy claim."""
from dataclasses import dataclass,asdict
from datetime import date,datetime,timedelta
from statistics import fmean
from typing import Protocol
from zoneinfo import ZoneInfo
from .inputs import InputError,number,iso
from .work import checkpoint

DAY=timedelta(days=1)
METHOD_ID='recent7-plus-past-heat-offset/v1'
METHOD={
 'id':METHOD_ID,
 'name':'Recent 7-day mean + past heat-period offset',
 'formula':'P = max(0, mean(last 7 complete days) + mean(past event mean − its preceding 7-day mean)); increase % = 100 × (P / current 7-day mean − 1)',
 'status':'simple_unvalidated_baseline',
 'additive7_match':'not_equivalent; frozen additive_7 uses ordinary-weather base7 and hierarchically pooled training-response deltas; see docs/ADDITIVE-7-RECONCILIATION.md',
 'reference_model_sha256':'63e41bc50487b7c6755cb96d9d65814a726a9421de26258cc47c7935a6ef80a7',
 'event_weighting':'equal weight per complete past heat event; daily means across the whole event',
 'minimum':'7 consecutive connected, zero-outage days and at least 1 complete eligible past heat event with its preceding 7 days',
 'claims':'No ML winner, real-world validated accuracy, weather causality, affordability score or automatic decision',
}

def day_range(start,end):
    a=date.fromisoformat(start); b=date.fromisoformat(end)
    if b<a: raise InputError('event end precedes start')
    result=[]
    for i in range((b-a).days+1):checkpoint();result.append((a+DAY*i).isoformat())
    return result

def complete_mean(index,start,end):
    """A missing/off-supply/outage day is unavailable, never a zero fill."""
    needed=day_range(start,end); values=[]
    for d in needed:
        checkpoint()
        row=index.get(d)
        if row is None: return None,'missing_usage_day'
        value=number(row.get('import_kwh'),field='consumption_daily.import_kwh',required=False,nonnegative=True)
        if value is None: return None,'missing_import_value'
        if row.get('supply_status')!='connected': return None,'supply_interruption'
        outage=number(row.get('outage_hours'),field='consumption_daily.outage_hours',required=False,nonnegative=True)
        if outage is None or outage>0: return None,'outage_or_unknown_outage'
        values.append(value)
    return fmean(values),None

def observed_event(index,event,cutoff):
    result={'event_id':event['id'],'start':event['start'],'end':event['end'],'duration':len(day_range(event['start'],event['end'])),'status':'unavailable','reason':None,'baseline':None,'observed':None,'delta_kwh':None,'increase_percent':None}
    if event.get('start_boundary')!='known_start' or event.get('end_boundary')!='known_end':
        result['reason']='partial_event_boundary';return result
    if event['end']>cutoff: result['reason']='event_not_completed_at_review';return result
    begin=date.fromisoformat(event['start'])
    before_start=(begin-7*DAY).isoformat();before_end=(begin-DAY).isoformat()
    baseline,reason=complete_mean(index,before_start,before_end)
    result.update(baseline=baseline,baseline_start=before_start,baseline_end=before_end)
    if reason: result['reason']=reason;return result
    actual,reason=complete_mean(index,event['start'],event['end']);result['observed']=actual
    if reason: result['reason']=reason;return result
    if baseline<=0: result['reason']='zero_comparison_baseline';return result
    result.update(status='available',reason=None,delta_kwh=actual-baseline,increase_percent=100*(actual/baseline-1))
    return result

class PredictionProvider(Protocol):
    def predict(self,usage,past_events,events,*,cutoff:str)->list[dict]: ...

@dataclass(frozen=True)
class InferenceContext:
    review_as_of:str
    history_cutoff:str
    horizon_start:str
    horizon_end:str
    weather_kind:str
    weather_retrieved_at:str|None=None
    weather_model_issued_at:str|None=None
    forecast_track:str|None=None

def predict_context(provider,usage,past_events,events,context):
    """Versioned application boundary; a future provider can consume context.

    Existing baseline keeps its own arithmetic. No synthetic mapping, forecast
    issue timestamp or frozen-model state is supplied by this wrapper.
    """
    review=datetime.fromisoformat(context.review_as_of.replace('Z','+00:00'))
    if review.tzinfo is None:raise InputError('review_as_of needs a UTC offset')
    cutoff=iso(context.history_cutoff,field='history_cutoff',required=True)
    start=iso(context.horizon_start,field='horizon_start',required=True);end=iso(context.horizon_end,field='horizon_end',required=True)
    local_day=review.astimezone(ZoneInfo('Australia/Perth')).date()
    if cutoff>=local_day or start!=local_day+DAY or end!=local_day+7*DAY:raise InputError('inference dates are outside the seven-day review contract')
    if context.weather_kind not in ('historical_replay','public_weather_forecast'):raise InputError('unknown weather kind')
    if context.weather_kind=='public_weather_forecast' and cutoff!=local_day-DAY:raise InputError('current predictions require usage through yesterday')
    retrieved=None
    for field in ('weather_retrieved_at','weather_model_issued_at'):
        value=getattr(context,field)
        if value is None:continue
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        if stamp.tzinfo is None:raise InputError(field+' needs a UTC offset')
        if field=='weather_retrieved_at':retrieved=stamp
        elif retrieved is None or stamp>retrieved:raise InputError('model issue cannot follow retrieval')
        if context.weather_kind=='public_weather_forecast' and stamp>review:raise InputError('weather was unavailable at the review time')
    for event in events:
        if not context.horizon_start<=event['start']<=event['end']<=context.horizon_end:raise InputError('event is outside the review horizon')
    if hasattr(provider,'predict_with_context'):
        return provider.predict_with_context(usage,past_events,events,context=context)
    return provider.predict(usage,past_events,events,cutoff=context.history_cutoff)

class Recent7HeatOffsetBaseline:
    """An explicit local baseline, not silently called the documented additive7."""
    method=METHOD
    def predict(self,usage,past_events,events,*,cutoff):
        # The provider itself enforces the business cutoff, even if a caller errs.
        index={}
        for row in usage:
            checkpoint()
            if row['date']>cutoff: continue
            if row['date'] in index: raise InputError('duplicate customer usage day')
            index[row['date']]=row
        last=date.fromisoformat(cutoff)
        first=(last-6*DAY).isoformat()
        baseline,reason=complete_mean(index,first,cutoff)
        history=[observed_event(index,e,cutoff) for e in past_events]
        usable=[r for r in history if r['status']=='available']
        offset=fmean(r['delta_kwh'] for r in usable) if usable else None
        results=[]
        for event in events:
            checkpoint()
            issue=reason
            if not issue and baseline<=0: issue='zero_current_baseline'
            if not issue and not usable: issue='no_complete_past_heat_comparison'
            if event.get('start_boundary')!='known_start' or event.get('end_boundary')!='known_end': issue='partial_event_boundary'
            if event['start']<=cutoff: issue='target_event_not_after_cutoff'
            predicted=None if issue else max(0,baseline+offset)
            results.append({'event_id':event['id'],'status':'unavailable' if issue else 'available','reason':issue,'method_id':METHOD_ID,'baseline':baseline,'baseline_start':first,'baseline_end':cutoff,'offset_kwh_per_day':offset,'past_events_used':len(usable),'past_event_inputs':history,'predicted':predicted,'increase':None if predicted is None else 100*(predicted/baseline-1),'duration':len(day_range(event['start'],event['end'])),'predicted_event_total':None if predicted is None else predicted*len(day_range(event['start'],event['end']))})
        return results
