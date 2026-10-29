"""Validated aggregate-only support join for the separate financial intake.

Only a reviewed manifest plus the exact customer/usage pair can produce context.
No individual risk, debt inference, income substitution or future activity model.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from business_upload import csv_rows, CUSTOMER_HEADERS, iso, derive_business
from source_adapter import require, digest, parse, SourceError

HEADERS = {
 'payment_arrangements.csv.gz': 'arrangement_id,customer_id,type,start_date,amount,instalment,n_instalments,end_date,status,trigger'.split(','),
 'hardship_programs.csv.gz': 'hardship_id,customer_id,assessment_date,trigger,assessment_outcome,debt_at_entry,start_date,instalment,exit_date,exit_reason,debt_at_exit,write_off,financial_counselling_referral,energy_efficiency_advice'.split(','),
 'hugs_grants.csv.gz': 'hugs_id,customer_id,application_date,payment_date,debt_at_application,grant_amount,outcome,region_cap,hardship_id'.split(','),
 'support_arrangement_history.csv.gz': 'history_id,arrangement_id,customer_id,arrangement_type,status,effective_from,effective_to,review_due_date,source_event_date,source_table'.split(','),
 'payments.csv.gz': 'payment_id,customer_id,date,amount,method,kind,status'.split(',')
}
MAX_ROWS = 1500000

def cents(value):
    try:
        x=Decimal(value)
        require(x.is_finite() and x>=0 and x==x.quantize(Decimal('.01')), 'financial_amount_invalid')
        return int(x*100)
    except (InvalidOperation,ValueError): raise SourceError('financial_amount_invalid') from None

def unavailable_support():
    return {'state':'unavailable','reason':'The two-file account/usage upload contains no support or grant history. Missing financial input is not zero.'}

def derive_support_context(customers_raw,usage_raw,compressed,trusted,today,business,sidecars,manifest_raw,reviewed_manifest_sha256):
    """Internal/offline preparation only. Bind every table to an approved manifest.

    Snapshot support counts use the existing active cohort at its recorded date.
    Monthly grant history describes ledger events for retained accounts, without
    asserting account activity on dates with no usage evidence.
    """
    require(type(manifest_raw) is bytes and len(manifest_raw)<=2*1024*1024,'financial_manifest_size')
    require(digest(manifest_raw)==reviewed_manifest_sha256,'reviewed_financial_manifest_hash_mismatch')
    manifest=parse(manifest_raw.decode('utf-8'));files=manifest.get('files',{})
    require(set(sidecars)==set(HEADERS),'complete_financial_sidecars_required')
    core,checks=derive_business(customers_raw,usage_raw,compressed,trusted,today)
    require(all(core.get(k)==business.get(k) for k in ['snapshotDate','customerSourceSha256','usageSourceSha256','totalAccounts','retainedTotalAccounts']), 'financial_cohort_or_snapshot_mismatch')
    require([(a['postcode'],a['accountCount']) for a in core['areas']]==[(a['postcode'],a['accountCount']) for a in business['areas']], 'financial_area_counts_mismatch')
    require(files.get('customers.csv',{}).get('sha256')==digest(customers_raw) and files.get('consumption_daily.csv.gz' if compressed else 'consumption_daily.csv',{}).get('sha256')==digest(usage_raw),'financial_manifest_core_mismatch')
    hashes={}
    for name,raw in sidecars.items():
        require(files.get(name,{}).get('sha256')==digest(raw),'financial_source_hash_mismatch')
        require(files[name].get('headers')==HEADERS[name],'financial_reviewed_schema_mismatch')
        hashes[name]=digest(raw)
    cutoff=iso(core['snapshotDate']);start=iso(core['historyStart'])
    customers={r['customer_id']:r for r in csv_rows(customers_raw,CUSTOMER_HEADERS)}
    # Same rule as the core uploader: a cutoff observation is mandatory.
    from business_upload import USAGE_HEADERS
    observed={r['customer_id'] for r in csv_rows(usage_raw,USAGE_HEADERS,compressed) if iso(r['date'])==cutoff}
    active={cid for cid,r in customers.items() if r['account_open_date'] and iso(r['account_open_date'])<=cutoff and (not r['account_close_date'] or iso(r['account_close_date'])>cutoff) and cid in observed}
    require(len(active)==core['totalAccounts'],'financial_activity_reconciliation')
    def day(value):
        d=iso(value);require(start<=d<=cutoff,'financial_event_outside_history');return d
    def rows(name):
        count=0
        for r in csv_rows(sidecars[name],HEADERS[name],True):
            count+=1;require(count<=MAX_ROWS,'financial_row_limit')
            require(r['customer_id'] in customers,'financial_customer_not_in_cohort')
            yield r
        require(count==files[name].get('rows'),'financial_manifest_row_count')
    parents={};seen=set()
    for name,key,typ,beg,end in [
        ('payment_arrangements.csv.gz','arrangement_id','payment_arrangements','start_date','end_date'),
        ('hardship_programs.csv.gz','hardship_id','hardship_programs','start_date','exit_date')]:
        for r in rows(name):
            ident=(typ,r[key]);require(ident not in parents,'duplicate_financial_parent')
            began=day(r[beg]) if r[beg] else None;terminal=day(r[end]) if r[end] else None
            require(not terminal or began and began<terminal,'financial_parent_interval')
            if typ=='hardship_programs':
                assessed=day(r['assessment_date']);require(r['assessment_outcome'] in {'accepted','denied'} and (r['assessment_outcome']=='accepted')==bool(began),'hardship_acceptance_start')
                require(not began or assessed<=began,'hardship_assessment_order')
            else:
                require(began is not None and r['type']=='payment_plan' and r['status'] in {'active','completed','broken','closed_account'} and (r['status']=='active')==(terminal is None),'payment_arrangement_state')
            parents[ident]=(r['customer_id'],began,terminal)
    support=defaultdict(lambda: {'payment':set(),'hardship':set()});intervals=defaultdict(list);covered_parents=set()
    for r in rows('support_arrangement_history.csv.gz'):
        require(r['history_id'] not in seen,'duplicate_support_history_id');seen.add(r['history_id'])
        typ=r['source_table'];parent=parents.get((typ,r['arrangement_id']))
        require(parent is not None and parent[0]==r['customer_id'],'support_parent_foreign_key')
        began=day(r['effective_from']);terminal=day(r['effective_to']) if r['effective_to'] else None
        require(not terminal or began<terminal,'support_interval')
        require(day(r['source_event_date'])==began,'support_event_date')
        require(r['status'] in {'active','completed','broken','closed_account','assessment_denied'},'support_status')
        if r['status']=='active':
            require((began,terminal)==parent[1:],'support_parent_interval')
            covered_parents.add((typ,r['arrangement_id']))
            expected_type='payment_plan' if typ=='payment_arrangements' else 'hardship_program'
            require(r['arrangement_type']==expected_type,'support_arrangement_type')
        elif r['status']!='assessment_denied': require(began==parent[2],'support_terminal_date')
        key=(typ,r['arrangement_id']);intervals[key].append((began,terminal))
        if r['status']=='active' and began<=cutoff and (terminal is None or cutoff<terminal) and r['customer_id'] in active:
            pc=customers[r['customer_id']]['postcode'];support[pc]['payment' if typ=='payment_arrangements' else 'hardship'].add(r['customer_id'])
    require(covered_parents=={key for key,parent in parents.items() if parent[1] is not None},'support_parent_history_incomplete')
    for spans in intervals.values():
        spans.sort()
        require(all(a[1] is not None and a[1]<=b[0] for a,b in zip(spans,spans[1:])),'overlapping_support_intervals')
    grants={}
    for r in rows('hugs_grants.csv.gz'):
        require(r['hugs_id'] not in grants,'duplicate_grant_id');parent=parents.get(('hardship_programs',r['hardship_id']))
        require(parent is not None and parent[0]==r['customer_id'] and parent[1] is not None,'grant_hardship_join')
        applied=day(r['application_date']);paid=day(r['payment_date']) if r['payment_date'] else None;amount=cents(r['grant_amount'])
        require(r['outcome'] in {'approved','declined'} and (paid is None or r['outcome']=='approved') and bool(paid)==bool(amount),'grant_payment_status')
        require(not paid or applied<=paid and parent[1]<=paid and (parent[2] is None or paid<parent[2]),'grant_payment_interval')
        grants[r['hugs_id']]=(r['customer_id'],paid,amount)
    matched=set();payment_ids=set();monthly=defaultdict(lambda:{'ids':set(),'count':0,'cents':0})
    for r in rows('payments.csv.gz'):
        require(r['payment_id'] not in payment_ids,'duplicate_payment_id');payment_ids.add(r['payment_id'])
        when=day(r['date']);amount=cents(r['amount'])
        require(r['status'] in {'cleared','dishonoured'},'payment_status')
        if r['kind']=='hugs_grant':
            require(r['status']=='cleared' and r['method']=='hugs_grant' and r['payment_id'].startswith('P_'),'grant_payment_record')
            gid=r['payment_id'][2:];require(gid in grants and grants[gid]==(r['customer_id'],when,amount),'grant_payment_join')
            require(gid not in matched,'duplicate_grant_payment');matched.add(gid)
            pc=customers[r['customer_id']]['postcode'];m=monthly[(pc,when.strftime('%Y-%m'))];m['ids'].add(r['customer_id']);m['count']+=1;m['cents']+=amount
        else: require(r['kind']=='bill_payment','unsupported_payment_kind')
    require(matched=={gid for gid,(_,paid,_) in grants.items() if paid},'paid_grant_without_cleared_payment')
    grant_recipients=defaultdict(set);grant_totals=defaultdict(lambda:{'count':0,'cents':0})
    for (pc,month),values in monthly.items():
        grant_recipients[pc].update(values['ids']);grant_totals[pc]['count']+=values['count'];grant_totals[pc]['cents']+=values['cents']
    areas=[]
    for a in core['areas']:
        pc=a['postcode'];s=support[pc]
        areas.append({'postcode':pc,'snapshotDate':core['snapshotDate'],'activeAccountDenominator':a['accountCount'],'activePaymentArrangementAccounts':len(s['payment']),'activeHardshipProgramAccounts':len(s['hardship']),'activeAccountsInEitherSupport':len(s['payment']|s['hardship']),'paidGrantRecipientsInPeriod':len(grant_recipients[pc]),'paidGrantRecipientsActiveAtSnapshot':len(grant_recipients[pc]&active),'paidGrantCountInPeriod':grant_totals[pc]['count'],'paidGrantAmountCentsInPeriod':grant_totals[pc]['cents']})
    return {'schemaVersion':2,'contract':'q3-financial-support-v2','historyStart':core['historyStart'],'historyEnd':core['historyEnd'],'coverage':{'accountPostcodes':sorted(a['postcode'] for a in core['areas']),'completeTables':sorted(HEADERS),'completeness':'Reviewed complete source tables for this exact retained cohort and recorded window; no claim of complete daily usage.'},'state':'validated','snapshotDate':core['snapshotDate'],'classification':'Historical synthetic support context; no individual risk score','cohortCustomerSha256':digest(customers_raw),'cohortUsageSha256':digest(usage_raw),'reviewedManifestSha256':reviewed_manifest_sha256,'sourceHashes':hashes,'areas':areas,'monthlyGrantLedger':[{'postcode':pc,'month':month,'retainedAccountsReceivingPaidGrant':len(v['ids']),'paidGrantCount':v['count'],'paidGrantAmountCents':v['cents']} for (pc,month),v in sorted(monthly.items())],'definitions':{'activeSupport':'Distinct accounts active at the business snapshot with a recorded active support interval; start inclusive, end exclusive. Arrangement and hardship counts can overlap; union counts once.','grantHistory':'Cleared, parent-joined grant ledger events for retained source accounts in the recorded month. Does not assert account activity at unobserved dates. Grant amounts are counted once, not added again from payments.','unavailable':'Missing sidecars produce unavailable context, never zero support counts.','paymentDifficulty':'Active arrangement participation is dated support context, not a general payment-difficulty or risk classification.'}}
