"""Read only the named candidate files. Writes a separate UI fixture and audit."""
import csv, gzip, hashlib, json, pathlib, collections, datetime
ROOT = pathlib.Path(__file__).resolve().parent
from prototype.inputs import DEFAULT_SOURCE
SOURCE = DEFAULT_SOURCE
META = json.loads((SOURCE/'SCHEMAS-AND-COVERAGE.json').read_text())
TABLES = {}
audit = []
for spec in META['files']:
    path = SOURCE/spec['file']
    op = gzip.open if path.suffix == '.gz' else open
    with op(path, 'rt', newline='') as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
        rows = list(reader)
    assert headers == spec['headers']
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == spec['sha256']
    assert len(rows) == spec['rows']
    actual_ranges = {}
    for datecol, expected in spec['date_ranges'].items():
        values = sorted(r[datecol][:10] for r in rows if r[datecol])
        actual_ranges[datecol] = [values[0], values[-1]]
        assert actual_ranges[datecol] == expected, (path.name, datecol, actual_ranges[datecol], expected)
    name = path.name.replace('.csv.gz','').replace('.csv','')
    TABLES[name] = rows
    key = {'customers':['customer_id'], 'customer_locations':['customer_id'], 'consumption_daily':['customer_id','date'], 'prepay_daily':['customer_id','date'], 'prepay_topups':['customer_id','datetime'], 'bills':['bill_id'], 'payments':['payment_id'], 'support_needs_history':['history_id'], 'support_arrangement_history':['history_id'], 'hardship_programs':['hardship_id'], 'hugs_grants':['hugs_id'], 'payment_arrangements':['arrangement_id']}[name]
    seen = collections.Counter(tuple(r[k] for k in key) for r in rows)
    audit.append(dict(file=spec['file'],sha256=digest,headers=headers,rows=len(rows),key=key,duplicate_keys=sum(v-1 for v in seen.values()),blank_counts={k:sum(r[k]=='' for r in rows) for k in headers},date_ranges=actual_ranges))
ids = ['C105002','C103794','C105013','C102031','C105017','C105072','C101456','C102502']
review='2025-01-02'
cutoff='2025-01-01'
# UI estimates/episode associations below are explicitly authored REVIEW FIXTURES.
# They are not source facts, weather-response calculations, or model outputs.
pcts=[(48,32),(42,30),(28,22),(18,12),(None,None),(None,8),(0,0),(60,45)]
past=[[(35,'2024-02-06','2024-02-10','Cooling cost difficulty')],[(25,'2024-02-06','2024-02-10','Bill extension'),(50,'2024-09-15','2024-09-19','Financial difficulty')],[(28,'2024-02-06','2024-02-10','Cooling cost difficulty')],[(15,'2024-02-23','2024-02-27','Payment plan')],[(20,'2024-02-06','2024-02-10','Cooling cost difficulty')],[(20,'2024-02-06','2024-02-10','Cooling cost difficulty')],[],[]]
customers=[]
for i, cid in enumerate(ids):
    c=next(r for r in TABLES['customers'] if r['customer_id']==cid)
    usage=[{k:r[k] for k in ['date','import_kwh','supply_status','outage_hours']} for r in TABLES['consumption_daily'] if r['customer_id']==cid and r['date']<=cutoff]
    episodes=[dict(id=f'FX-{cid}-{j}',increase_percent=n,start=s,end=e,label=l,linked=True,provenance='authored_review_fixture') for j,(n,s,e,l) in enumerate(past[i])]
    if cid=='C102502': episodes=[dict(id='FX-UNLINKED',increase_percent=10,start='2024-09-05',end='2024-09-05',label='Bill extension',linked=False,provenance='authored_review_fixture')]
    financial=[]
    if c['prepayment_meter']=='True':
        rows=[r for r in TABLES['prepay_daily'] if r['customer_id']==cid and r['date']<=cutoff]
        financial=[dict(kind='Prepaid closing credit',date=r['date'],amount=r['closing_credit'],source='prepay_daily.closing_credit') for r in rows[-1:]]
    else:
        rows=[r for r in TABLES['bills'] if r['customer_id']==cid and r['issue_date']<=review]
        financial=[dict(kind='Bill issued',date=r['issue_date'],amount=r['amount_due'],source='bills.amount_due') for r in rows[-3:]]
    records=[]
    for name,datecol,idcol,label in [('payment_arrangements','start_date','arrangement_id','Arrangement started'),('hardship_programs','assessment_date','hardship_id','Hardship assessed'),('hugs_grants','application_date','hugs_id','Grant application'),('support_needs_history','source_event_date','need_id','Difficulty recorded')]:
        seen=set()
        for r in TABLES[name]:
            if r['customer_id']==cid and r[datecol]<=review and r[idcol] not in seen:
                seen.add(r[idcol]); records.append(dict(id=r[idcol],kind=label,date=r[datecol],source=name+'.'+datecol))
    customers.append(dict(customer=c,usage=usage,episodes=episodes,expected_percent_fixture=list(pcts[i]),financial=financial,records=records))
weather_path=SOURCE/'Fitzroy-Crossing-6765-HISTORICAL-INPUTS/Fitzroy-Crossing-6765-observed-interpolated-SILO-2023-07-01_to_2025-06-30.csv'
weather_all=list(csv.DictReader(weather_path.open()))
assert len(weather_all)==731
assert min(r['date'] for r in weather_all)=='2023-07-01'
assert max(r['date'] for r in weather_all)=='2025-06-30'
weather=[{k:r[k] for k in ['date','postcode','max_temp','min_temp']} for r in weather_all if r['date']<='2025-01-09']
fixture=dict(version='q1-ui-review-v1',review_date=review,history_cutoff=cutoff,horizon_start='2025-01-03',horizon_end='2025-01-09',history_window_start='2023-01-02',history_available_start='2023-07-01',customers=customers,weather=weather,events=[dict(id='A',label='Event A',start='2025-01-03',end='2025-01-05',category='Heat review fixture'),dict(id='B',label='Event B',start='2025-01-07',end='2025-01-09',category='Heat review fixture')],provenance=dict(business='Unchanged synthetic candidate source rows, subset only',estimates='Hand-authored percentages for UI review. No predictive model.',episode_links='Hand-authored associations and comparisons for UI review. No heat-event linkage in source.',weather='SILO interpolated historical observations. Hindsight, not as-issued forecasts.',baseline='UI illustration: preceding 14 completed days mean import_kwh. Not an agreed forecast baseline.'))
(ROOT/'assets/review-fixture.json').write_text(json.dumps(fixture,separators=(',',':'))+'\n')
known={r['customer_id'] for r in TABLES['customers']}
for name,rows in TABLES.items():
    assert all(r['customer_id'] in known for r in rows)
report=dict(status='read-only inspection; no business schema changes',files=audit,all_customer_foreign_keys_valid=True,weather=dict(file=str(weather_path),sha256=hashlib.sha256(weather_path.read_bytes()).hexdigest(),headers=next(csv.reader(weather_path.open())),rows=len(weather_all),dates=[min(r['date'] for r in weather_all),max(r['date'] for r in weather_all)]),units=dict(grid_import='kWh per day',export='kWh per day, separate from import',money='dollars; AUD working assumption only',temperature='degrees Celsius',rain='mm per day',time='ISO dates, source timezone unspecified'))
(ROOT/'docs/source-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'files_verified':len(audit),'source_rows':sum(x['rows'] for x in audit),'fixture_customers':len(customers),'duplicate_keys':{x['file']:x['duplicate_keys'] for x in audit if x['duplicate_keys']}}))
