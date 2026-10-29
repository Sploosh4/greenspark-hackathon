"""Content-validated synthetic financial intake; uploader hashes confer no trust.

No uploaded code is executed. The HTTP path derives every aggregate server-side.
Runtime receipts record this validation, not an authenticated generator identity.
"""
import gzip,io,json,re,zlib
from datetime import timedelta
from decimal import Decimal
from collections import Counter
from business_upload import csv_rows,CUSTOMER_HEADERS,USAGE_HEADERS,iso,derive_business
from financial_support import HEADERS,derive_support_context
from source_adapter import SourceError,require,canonical,digest

POLICY='q3-synthetic-financial-v1'
CONTRACT='q3-financial-support-v3'
MAX_ENCODED=16*1024*1024
MAX_EXPANDED=96*1024*1024
MAX_BATCH_EXPANDED=256*1024*1024
MAX_FINANCIAL_ROWS=2000000
MAX_PARENT_ROWS=200000
MAX_HISTORY_ROWS=400000
MAX_CENTS=10**12
SAFE=9007199254740991
BASE_KEYS={'schemaVersion','contract','historyStart','historyEnd','coverage','state','snapshotDate','classification','cohortCustomerSha256','cohortUsageSha256','sourceManifestSha256','sourceHashes','areas','monthlyGrantLedger','definitions','validation'}
CLASSIFICATION='Validated synthetic source-table support context; no individual risk score'
COMPLETENESS='Declared complete synthetic source tables for this cohort and window; internally validated, not independent evidence of real-world completeness or complete daily usage.'
PROVENANCE='Uploader-declared generator metadata; not authenticated origin or real customer observations'
AREA_KEYS={'postcode','snapshotDate','activeAccountDenominator','activePaymentArrangementAccounts','activeHardshipProgramAccounts','activeAccountsInEitherSupport','paidGrantRecipientsInPeriod','paidGrantRecipientsActiveAtSnapshot','paidGrantCountInPeriod','paidGrantAmountCentsInPeriod'}
LEDGER_KEYS={'postcode','month','retainedAccountsReceivingPaidGrant','paidGrantCount','paidGrantAmountCents'}
HASH=re.compile(r'[0-9a-f]{64}')
ID=re.compile(r'[A-Za-z0-9_:.~-]{1,128}')
MONEY=re.compile(r'(?:0|[1-9][0-9]{0,10})(?:\.[0-9]{1,2})?')
NUMBER=re.compile(r'(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,6})?')
NAMES=['customers.csv','consumption_daily.csv.gz',*sorted(HEADERS)]

def ishash(x):return type(x) is str and HASH.fullmatch(x) is not None

def bounded_int(x,limit,minimum=0):return type(x) is int and minimum<=x<=limit

def money(value,positive=False):
    require(type(value) is str and MONEY.fullmatch(value) is not None,'synthetic_financial_money_format')
    result=int(Decimal(value)*100)
    require((result>0 if positive else result>=0) and result<=MAX_CENTS,'synthetic_financial_money_bounds')
    return result

def identifier(value):
    require(type(value) is str and ID.fullmatch(value) is not None,'synthetic_financial_identifier')
    return value

def text(value,maximum=256):
    require(type(value) is str and 0<len(value)<=maximum and all(ord(c)>=32 and ord(c)!=127 for c in value),'synthetic_financial_text')
    return value

def load_manifest(raw):
    require(type(raw) is bytes and 0<len(raw)<=2*1024*1024,'financial_manifest_size')
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'synthetic_financial_duplicate_json_key');d[k]=v
        return d
    try:
        d=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(SourceError('synthetic_financial_nonfinite_json')))
    except (UnicodeError,json.JSONDecodeError,RecursionError):raise SourceError('synthetic_financial_manifest_json') from None
    require(type(d) is dict,'synthetic_financial_manifest_contract')
    return d

def manifest_contract(raw,business):
    m=load_manifest(raw)
    require(m.get('synthetic_financial_contract')==POLICY and m.get('synthetic') is True,'synthetic_financial_policy_declaration')
    text(m.get('generator'),128);require(ishash(m.get('generator_source_sha256')),'synthetic_financial_generator_metadata')
    if 'tool_revision' in m:text(m['tool_revision'],128)
    require(m.get('geography_sha256')==business.get('geographyRegistrySha256') and ishash(m.get('geography_sha256')),'financial_geography_mismatch')
    p=m.get('parameters');require(type(p) is dict and p.get('profile')=='season-ahead','synthetic_financial_parameters')
    require(bounded_int(p.get('count'),100000,1) and p['count']==business['retainedTotalAccounts'] and bounded_int(p.get('seed'),2**63-1),'synthetic_financial_parameters')
    require(p.get('start')==business['historyStart'] and p.get('end')==business['historyEnd']==business['snapshotDate'],'financial_manifest_window_or_cohort')
    pcs=sorted(a['postcode'] for a in business['areas']);coverage=m.get('financial_coverage')
    if 'postcodes' in p:require(type(p['postcodes']) is list and all(type(pc) is str for pc in p['postcodes']) and len(p['postcodes'])==len(pcs) and sorted(p['postcodes'])==pcs,'synthetic_financial_parameters')
    if 'dense' in p:require(type(p['dense']) is bool,'synthetic_financial_parameters')
    require(type(coverage) is dict and set(coverage)=={'accountPostcodes','historyStart','historyEnd','declaration'} and coverage.get('accountPostcodes')==pcs and coverage.get('historyStart')==business['historyStart'] and coverage.get('historyEnd')==business['historyEnd'] and coverage.get('declaration')=='complete-synthetic-source-tables','synthetic_financial_coverage_declaration')
    files=m.get('files');require(type(files) is dict and set(NAMES)<=set(files)<=set(NAMES)|{'coverage.csv'},'synthetic_financial_manifest_files')
    for name in NAMES:
        f=files[name];headers=CUSTOMER_HEADERS if name=='customers.csv' else USAGE_HEADERS if name=='consumption_daily.csv.gz' else HEADERS[name]
        limit=100000 if name=='customers.csv' else MAX_PARENT_ROWS if name in {'payment_arrangements.csv.gz','hardship_programs.csv.gz'} else MAX_HISTORY_ROWS if name=='support_arrangement_history.csv.gz' else 1500000
        require(type(f) is dict and ishash(f.get('sha256')) and f.get('headers')==headers and bounded_int(f.get('bytes'),MAX_ENCODED,1) and bounded_int(f.get('expandedBytes'),MAX_EXPANDED,1) and bounded_int(f.get('rows'),limit,1 if name in NAMES[:2] else 0),'synthetic_financial_manifest_file_metadata')
    require(sum(files[n]['expandedBytes'] for n in NAMES)<=MAX_BATCH_EXPANDED,'synthetic_financial_expanded_batch_limit')
    require(sum(files[n]['rows'] for n in HEADERS)<=MAX_FINANCIAL_ROWS,'synthetic_financial_total_row_limit')
    return m

def derive_synthetic_context(customers_raw,usage_raw,trusted,today,business,sidecars,manifest_raw):
    """Strict raw-table validation precedes server-derived v3 support context."""
    m=manifest_contract(manifest_raw,business)
    require(type(sidecars) is dict and set(sidecars)==set(HEADERS),'complete_financial_sidecars_required')
    source={'customers.csv':customers_raw,'consumption_daily.csv.gz':usage_raw,**sidecars}
    require(all(type(v) is bytes for v in source.values()),'synthetic_financial_source_bytes')
    require(sum(map(len,source.values()))+len(manifest_raw)<=32*1024*1024,'financial_upload_size_limit')
    require(digest(customers_raw)==business['customerSourceSha256'] and digest(usage_raw)==business['usageSourceSha256'],'financial_cohort_mismatch')
    metrics={};expanded_total=0
    for name in NAMES:
        raw=source[name];f=m['files'][name]
        require(0<len(raw)<=MAX_ENCODED and len(raw)==f['bytes'] and digest(raw)==f['sha256'],'financial_source_hash_or_size_mismatch')
        expanded=0
        try:
            stream=gzip.GzipFile(fileobj=io.BytesIO(raw)) if name.endswith('.gz') else io.BytesIO(raw)
            with stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):
                    expanded+=len(chunk);expanded_total+=len(chunk)
                    require(expanded<=MAX_EXPANDED and expanded_total<=MAX_BATCH_EXPANDED,'synthetic_financial_expanded_limit')
        except (OSError,EOFError,zlib.error):raise SourceError('invalid_csv_or_gzip') from None
        require(expanded==f['expandedBytes'],'synthetic_financial_expanded_size_mismatch')
        metrics[name]={'rows':0,'encodedBytes':len(raw),'expandedBytes':expanded}
    financial_rows=0
    def rows(name):
        nonlocal financial_rows
        headers=CUSTOMER_HEADERS if name=='customers.csv' else USAGE_HEADERS if name=='consumption_daily.csv.gz' else HEADERS[name]
        for row in csv_rows(source[name],headers,name.endswith('.gz')):
            metrics[name]['rows']+=1
            require(metrics[name]['rows']<=m['files'][name]['rows'],'synthetic_financial_actual_row_count')
            if name in HEADERS:
                financial_rows+=1;require(financial_rows<=MAX_FINANCIAL_ROWS,'synthetic_financial_total_row_limit')
            yield row
        require(metrics[name]['rows']==m['files'][name]['rows'],'synthetic_financial_actual_row_count')
    customers={};cutoff=iso(business['snapshotDate']);start=iso(business['historyStart'])
    def day(value,cid=None,optional=False):
        if optional and value=='':return None
        d=iso(value);require(start<=d<=cutoff,'financial_event_outside_history')
        if cid is not None:
            opened,closed=customers[cid]
            require((opened is None or opened<=d) and (closed is None or d<=closed),'synthetic_financial_event_account_lifecycle')
        return d
    for r in rows('customers.csv'):
        cid=identifier(r['customer_id']);require(cid not in customers,'duplicate_customer_id')
        opened=iso(r['account_open_date'],True);closed=iso(r['account_close_date'],True)
        customers[cid]=(opened,closed)
        for k in ['prepayment_meter','has_solar','concession_card','life_support','medical_cooling_subsidy','interpreter_required']:
            require(r[k] in {'True','False'},'synthetic_financial_customer_boolean')
        require(NUMBER.fullmatch(r['solar_kw']) is not None,'synthetic_financial_customer_solar')
        solar=Decimal(r['solar_kw']);require(solar<=10000 and (solar>0)==(r['has_solar']=='True'),'synthetic_financial_customer_solar')
        require(bool(r['life_support_registered_date'])==(r['life_support']=='True'),'synthetic_financial_customer_registration')
        if r['life_support_registered_date']:require(iso(r['life_support_registered_date'])<=cutoff,'synthetic_financial_customer_registration')
    for r in rows('consumption_daily.csv.gz'):
        require(r['customer_id'] in customers,'usage_customer_not_in_customer_file')
        values=[]
        for k in USAGE_HEADERS[2:7]+['outage_hours']:
            require(NUMBER.fullmatch(r[k]) is not None,'synthetic_financial_usage_number');v=Decimal(r[k]);require(v<=10**9,'synthetic_financial_usage_number');values.append(v)
        require(values[0]==sum(values[1:4]) and values[-1]<=24,'synthetic_financial_usage_components')
    core,_=derive_business(customers_raw,usage_raw,True,trusted,today)
    require(all(core.get(k)==business.get(k) for k in ['snapshotDate','customerSourceSha256','usageSourceSha256','totalAccounts','retainedTotalAccounts','geographyRegistrySha256','areas']),'financial_cohort_or_snapshot_mismatch')
    parents={};seen_history=set();history=Counter()
    for name,key,typ in [('payment_arrangements.csv.gz','arrangement_id','payment_arrangements'),('hardship_programs.csv.gz','hardship_id','hardship_programs')]:
        for r in rows(name):
            cid=r['customer_id'];require(cid in customers,'financial_customer_not_in_cohort');ident=(typ,identifier(r[key]));require(ident not in parents,'duplicate_financial_parent')
            if typ=='payment_arrangements':
                require(r['type']=='payment_plan' and r['status'] in {'active','completed','broken','closed_account'},'synthetic_financial_parent_state')
                began=day(r['start_date'],cid);terminal=day(r['end_date'],cid,True);text(r['trigger'])
                require(re.fullmatch(r'[1-9][0-9]{0,5}',r['n_instalments']) is not None,'synthetic_financial_instalment_count')
                amount=money(r['amount'],True);instalment=money(r['instalment'],True)
                require(amount==instalment*int(r['n_instalments']),'synthetic_financial_instalment_total')
                require((r['status']=='active')==(terminal is None),'synthetic_financial_parent_state')
                terminal_status=r['status'] if terminal else None;assessed=None
            else:
                assessed=day(r['assessment_date'],cid);require(r['assessment_outcome'] in {'accepted','denied'},'hardship_acceptance_start');text(r['trigger'])
                began=day(r['start_date'],cid,True);terminal=day(r['exit_date'],cid,True)
                require((r['assessment_outcome']=='accepted')==(began is not None),'hardship_acceptance_start')
                money(r['debt_at_entry']);writeoff=money(r['write_off'])
                for k in ['financial_counselling_referral','energy_efficiency_advice']:require(r[k] in {'True','False'},'synthetic_financial_hardship_boolean')
                if began:money(r['instalment'],True);require(assessed<=began,'hardship_assessment_order')
                else:require(not terminal and r['instalment'] in {'','0','0.00'},'synthetic_financial_parent_state')
                if terminal:money(r['debt_at_exit']);text(r['exit_reason'])
                else:require(r['debt_at_exit']=='' and r['exit_reason']=='' and writeoff==0,'synthetic_financial_parent_state')
                terminal_status=None
            require(terminal is None or began is not None and began<terminal,'financial_parent_interval')
            closed=customers[cid][1]
            require(began is None or closed is None or closed>cutoff or terminal is not None and terminal<=closed,'synthetic_financial_open_support_after_closure')
            if terminal_status=='closed_account':require(closed==terminal,'synthetic_financial_closed_account_event')
            parents[ident]={'cid':cid,'begin':began,'end':terminal,'terminalStatus':terminal_status,'assessed':assessed}
    for r in rows('support_arrangement_history.csv.gz'):
        ident=identifier(r['history_id']);require(ident not in seen_history,'duplicate_support_history_id');seen_history.add(ident)
        cid=r['customer_id'];require(cid in customers,'financial_customer_not_in_cohort')
        key=(r['source_table'],identifier(r['arrangement_id']));parent=parents.get(key);require(parent is not None and parent['cid']==cid,'support_parent_foreign_key')
        expected='payment_plan' if key[0]=='payment_arrangements' else 'hardship_program';require(r['arrangement_type']==expected,'support_arrangement_type')
        began=day(r['effective_from'],cid);end=day(r['effective_to'],cid,True);require(day(r['source_event_date'],cid)==began,'support_event_date')
        status=r['status'];require(status in {'active','completed','broken','closed_account','assessment_denied'},'support_status')
        if status=='active':
            require(parent['begin'] is not None and (began,end)==(parent['begin'],parent['end']),'support_parent_interval')
            if r['review_due_date']:require(began<=iso(r['review_due_date'])<=cutoff+timedelta(days=366),'synthetic_financial_review_date')
            history[(key,'active')]+=1
        elif status=='assessment_denied':
            require(key[0]=='hardship_programs' and parent['begin'] is None and began==parent['assessed'] and end is None and r['review_due_date']=='','synthetic_financial_denied_history')
            history[(key,'denied')]+=1
        else:
            require(parent['end'] is not None and began==parent['end'] and end is None and r['review_due_date']=='','support_terminal_date')
            require(parent['terminalStatus'] in {None,status},'synthetic_financial_terminal_status')
            if status=='closed_account':require(customers[cid][1]==began,'synthetic_financial_closed_account_event')
            history[(key,'terminal')]+=1
    for key,parent in parents.items():
        require(history[(key,'active')]==(1 if parent['begin'] else 0) and history[(key,'terminal')]==(1 if parent['end'] else 0) and history[(key,'denied')]==(0 if parent['begin'] else 1),'synthetic_financial_parent_history_complete')
    grants={}
    for r in rows('hugs_grants.csv.gz'):
        gid=identifier(r['hugs_id']);require(gid not in grants,'duplicate_grant_id');cid=r['customer_id'];require(cid in customers,'financial_customer_not_in_cohort')
        parent=parents.get(('hardship_programs',identifier(r['hardship_id'])));require(parent is not None and parent['cid']==cid and parent['begin'] is not None,'grant_hardship_join')
        applied=day(r['application_date'],cid);paid=day(r['payment_date'],cid,True);amount=money(r['grant_amount']);debt=money(r['debt_at_application']);cap=money(r['region_cap'],True)
        require(amount<=debt and amount<=cap,'synthetic_financial_grant_debt_or_cap')
        require(r['outcome'] in {'approved','declined'} and (paid is None or r['outcome']=='approved') and bool(paid)==bool(amount),'grant_payment_status')
        require(parent['begin']<=applied and (parent['end'] is None or applied<parent['end']) and (paid is None or applied<=paid and (parent['end'] is None or paid<parent['end'])),'grant_payment_interval')
        grants[gid]=(cid,paid,amount)
    payment_ids=set();paid_grants=set();total_paid_cents=0
    for r in rows('payments.csv.gz'):
        pid=identifier(r['payment_id']);require(pid not in payment_ids,'duplicate_payment_id');payment_ids.add(pid);cid=r['customer_id'];require(cid in customers,'financial_customer_not_in_cohort')
        when=day(r['date'],cid);amount=money(r['amount'],True)
        require(r['status'] in {'cleared','dishonoured'} and r['kind'] in {'bill_payment','hugs_grant'},'synthetic_financial_payment_state')
        if r['kind']=='hugs_grant':
            require(r['status']=='cleared' and r['method']=='hugs_grant' and pid.startswith('P_'),'grant_payment_record');gid=pid[2:]
            require(gid in grants and grants[gid]==(cid,when,amount) and gid not in paid_grants,'grant_payment_join');paid_grants.add(gid);total_paid_cents+=amount
            require(total_paid_cents<=SAFE,'synthetic_financial_aggregate_amount_bounds')
        else:require(r['method'] in {'online_bpay','prepayment_topup','direct_debit','centrepay','card','cash','bank_transfer','other'},'synthetic_financial_payment_method')
    require(paid_grants=={g for g,(_,paid,_) in grants.items() if paid},'paid_grant_without_cleared_payment')
    support=derive_support_context(customers_raw,usage_raw,True,trusted,today,business,sidecars,manifest_raw,digest(manifest_raw))
    support['schemaVersion']=3;support['contract']=CONTRACT;support['classification']=CLASSIFICATION;support['sourceManifestSha256']=support.pop('reviewedManifestSha256');support['coverage']['completeness']=COMPLETENESS
    support['validation']={'policy':POLICY,'synthetic':True,'geographyRegistrySha256':business['geographyRegistrySha256'],'generator':{'name':m['generator'],'revision':m.get('tool_revision',m['generator']),'sourceSha256':m['generator_source_sha256'],'seed':str(m['parameters']['seed']),'assertion':PROVENANCE},'files':metrics,'aggregateSha256':digest(canonical(support))}
    validate_synthetic_attachment(support,business)
    return support

def validate_synthetic_attachment(s,b):
    """Validate a server-derived receipt on promotion and local restart.

    No endpoint accepts an uploaded aggregate/receipt. Hashes detect binding drift;
    filesystem ownership protects saved state, not a claim of signed attestation.
    """
    require(type(s) is dict and set(s)==BASE_KEYS and type(s.get('schemaVersion')) is int and s['schemaVersion']==3 and s.get('contract')==CONTRACT and s.get('state')=='validated','financial_attachment_contract')
    require(s.get('classification')==CLASSIFICATION and ishash(s.get('sourceManifestSha256')),'synthetic_financial_attachment_provenance')
    require(s.get('snapshotDate')==b['snapshotDate'] and s.get('historyStart')==b['historyStart'] and s.get('historyEnd')==b['historyEnd'] and s.get('cohortCustomerSha256')==b['customerSourceSha256'] and s.get('cohortUsageSha256')==b['usageSourceSha256'],'financial_cohort_mismatch')
    v=s.get('validation');require(type(v) is dict and set(v)=={'policy','synthetic','geographyRegistrySha256','generator','files','aggregateSha256'} and v.get('policy')==POLICY and v.get('synthetic') is True and v.get('geographyRegistrySha256')==b.get('geographyRegistrySha256'),'synthetic_financial_validation_receipt')
    g=v['generator'];require(type(g) is dict and set(g)=={'name','revision','sourceSha256','seed','assertion'} and g.get('assertion')==PROVENANCE and ishash(g.get('sourceSha256')),'synthetic_financial_validation_receipt');text(g.get('name'),128);text(g.get('revision'),128)
    require(type(g.get('seed')) is str and re.fullmatch(r'0|[1-9][0-9]{0,18}',g['seed']) is not None and int(g['seed'])<=2**63-1,'synthetic_financial_validation_receipt')
    unsigned={k:val for k,val in s.items() if k!='validation'};require(v.get('aggregateSha256')==digest(canonical(unsigned)),'financial_aggregate_integrity')
    metrics=v['files'];require(type(metrics) is dict and set(metrics)==set(NAMES),'synthetic_financial_validation_receipt')
    for name,f in metrics.items():
        limit=100000 if name=='customers.csv' else MAX_PARENT_ROWS if name in {'payment_arrangements.csv.gz','hardship_programs.csv.gz'} else MAX_HISTORY_ROWS if name=='support_arrangement_history.csv.gz' else 1500000
        require(type(f) is dict and set(f)=={'rows','encodedBytes','expandedBytes'} and bounded_int(f.get('rows'),limit,1 if name in NAMES[:2] else 0) and bounded_int(f.get('encodedBytes'),MAX_ENCODED,1) and bounded_int(f.get('expandedBytes'),MAX_EXPANDED,1),'synthetic_financial_validation_receipt')
    require(sum(f['encodedBytes'] for f in metrics.values())<=32*1024*1024 and sum(f['expandedBytes'] for f in metrics.values())<=MAX_BATCH_EXPANDED and sum(metrics[n]['rows'] for n in HEADERS)<=MAX_FINANCIAL_ROWS and metrics['customers.csv']['rows']==b['retainedTotalAccounts'],'synthetic_financial_validation_receipt')
    pcs=sorted(a['postcode'] for a in b['areas']);coverage=s.get('coverage');require(type(coverage) is dict and set(coverage)=={'accountPostcodes','completeTables','completeness'} and coverage.get('accountPostcodes')==pcs and coverage.get('completeTables')==sorted(HEADERS) and coverage.get('completeness')==COMPLETENESS,'financial_coverage_mismatch')
    hashes=s.get('sourceHashes');require(type(hashes) is dict and set(hashes)==set(HEADERS) and all(ishash(h) for h in hashes.values()),'synthetic_financial_attachment_provenance')
    areas=s.get('areas');require(type(areas) is list and len(areas)==len(pcs) and [a.get('postcode') for a in areas if type(a) is dict]==pcs,'financial_area_coverage')
    known={a['postcode']:a for a in b['areas']};by_pc={};totals={pc:[0,0,0,0] for pc in pcs}
    for a in areas:
        require(set(a)==AREA_KEYS and a['snapshotDate']==b['snapshotDate'] and all(bounded_int(a[k],SAFE) for k in AREA_KEYS-{'postcode','snapshotDate'}),'financial_area_schema')
        n=a['activeAccountDenominator'];p=a['activePaymentArrangementAccounts'];h=a['activeHardshipProgramAccounts'];u=a['activeAccountsInEitherSupport'];rec=a['paidGrantRecipientsInPeriod'];count=a['paidGrantCountInPeriod'];amount=a['paidGrantAmountCentsInPeriod']
        require(n==known[a['postcode']]['accountCount'] and max(p,h)<=u<=min(n,p+h) and a['paidGrantRecipientsActiveAtSnapshot']<=min(n,rec) and rec<=min(known[a['postcode']]['retainedAccountCount'],count) and (rec==0)==(count==0)==(amount==0),'financial_count_or_amount_invalid');by_pc[a['postcode']]=a
    ledger=s.get('monthlyGrantLedger');require(type(ledger) is list and len(ledger)<=min(1500000,len(pcs)*1200),'synthetic_financial_grant_ledger')
    seen=set();order=[]
    for row in ledger:
        require(type(row) is dict and set(row)==LEDGER_KEYS and type(row.get('postcode')) is str and row['postcode'] in known and type(row.get('month')) is str and re.fullmatch(r'[0-9]{4}-(?:0[1-9]|1[0-2])',row['month']) is not None,'synthetic_financial_grant_ledger')
        pc=row['postcode'];key=(pc,row['month']);require(key not in seen and b['historyStart'][:7]<=row['month']<=b['historyEnd'][:7],'synthetic_financial_grant_ledger');seen.add(key);order.append(key)
        count=row['paidGrantCount'];rec=row['retainedAccountsReceivingPaidGrant'];amount=row['paidGrantAmountCents'];require(all(bounded_int(row[k],SAFE,1) for k in ['paidGrantCount','retainedAccountsReceivingPaidGrant','paidGrantAmountCents']) and rec<=min(count,known[pc]['retainedAccountCount'],by_pc[pc]['paidGrantRecipientsInPeriod']),'synthetic_financial_grant_ledger')
        t=totals[pc];t[0]+=count;t[1]+=amount;t[2]+=rec;t[3]=max(t[3],rec);require(all(x<=SAFE for x in t),'synthetic_financial_aggregate_amount_bounds')
    require(order==sorted(order),'synthetic_financial_grant_ledger')
    for pc,t in totals.items():
        a=by_pc[pc];require(a['paidGrantCountInPeriod']==t[0] and a['paidGrantAmountCentsInPeriod']==t[1] and t[3]<=a['paidGrantRecipientsInPeriod']<=t[2],'synthetic_financial_grant_period_reconciliation')
    require(type(s.get('definitions')) is dict and all(type(k) is str and type(v) is str and len(k)<=64 and len(v)<=2048 for k,v in s['definitions'].items()),'synthetic_financial_definitions')
    return s
