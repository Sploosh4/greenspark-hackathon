"""Pure dry-run release planner. No network, credentials, jobs or scheduler."""
from datetime import date,timedelta
import re
from source_adapter import SourceError, require

def issue_month(value):
    require(isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}',value),'invalid_issue_month')
    try:return date.fromisoformat(value+'-01')
    except ValueError:raise SourceError('invalid_issue_month') from None

def months(issue):
    d=issue_month(issue)
    return [f'{d.year+(d.month-1+i)//12:04d}-{(d.month-1+i)%12+1:02d}' for i in range(6)]

def plan_release(today,active_issue,candidate_issue,availability,*,reviewed_lag_days=None,successful=(),in_flight=()):
    """A nominal release date is eligibility to check, never proof of availability.

    availability: {mean: bool, anomaly: bool}; caller supplies verified catalogue
    evidence in a future worker. This function never fetches that evidence.
    """
    active=issue_month(active_issue);candidate=issue_month(candidate_issue)
    key=f'ecmwf:51:{candidate_issue}:t2m:mean+anomaly:leads1-6:wa-v1'
    result={'mode':'dry_run','issue':candidate_issue,'key':key,'keepActiveIssue':active_issue,'activate':False,'submitJob':False,'validMonths':months(candidate_issue)}
    if candidate<=active or key in successful:return {**result,'action':'already_successful_or_older'}
    if key in in_flight:return {**result,'action':'already_in_flight'}
    if reviewed_lag_days is None:return {**result,'action':'configuration_review_required'}
    require(type(reviewed_lag_days) is int and 0<=reviewed_lag_days<=14,'invalid_release_lag')
    eligible=candidate.replace(day=6)+timedelta(days=reviewed_lag_days)
    if today<eligible:return {**result,'action':'wait_for_nominal_release_plus_lag','eligibleFrom':eligible.isoformat()}
    require(type(availability) is dict and all(type(availability.get(k)) is bool for k in ['mean','anomaly']),'availability_evidence_required')
    if not all(availability.values()):return {**result,'action':'wait_for_both_sources','eligibleFrom':eligible.isoformat()}
    return {**result,'action':'ready_for_reviewed_retrieval','eligibleFrom':eligible.isoformat()}

def replacement_decision(candidate,active_issue):
    """Fixture contract for a future decoded pack, before atomic bundle promotion."""
    require(type(candidate) is dict,'candidate_required')
    issue=candidate.get('issueMonth');issue_month(issue)
    if issue<=active_issue:return 'keep_latest_success'
    require(candidate.get('meanIssueMonth')==candidate.get('anomalyIssueMonth')==issue,'mixed_issue_pack')
    require(candidate.get('validMonths')==months(issue),'verifying_month_mismatch')
    require(candidate.get('gridAligned') is True and candidate.get('unitsValidated') is True and candidate.get('hashesVerified') is True and candidate.get('missingnessValidated') is True,'decoded_pack_not_validated')
    return 'candidate_ready_for_atomic_validation'
