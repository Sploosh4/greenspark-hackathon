"""Build small browser inputs from the canonical release; never run its generators."""
import argparse, csv, gzip, hashlib, json
from decimal import Decimal
from collections import defaultdict
from pathlib import Path

def build(source, out):
    def rows(name):
        path = source / name
        with (gzip.open(path, 'rt') if name.endswith('.gz') else path.open()) as f:
            return list(csv.DictReader(f))
    selection = json.loads((source/'selection_manifest.json').read_text())
    assert selection['version'] == 'complete-scenario-2025Q1-v1'
    customers = rows('base/customers.csv')
    locations = {r['customer_id']:r for r in rows('base/customer_locations.csv')}
    rules = {r['customer_id']:r for r in rows('financial/data/prepaid_account_rules.csv')}
    topups = rows('financial/data/prepaid_topups.csv')
    at_noon = defaultdict(int)
    for r in topups:
        if r['datetime'][11:19] == '12:00:00':
            at_noon[(r['customer_id'], r['datetime'][:10])] += int(r['amount_cents'])
    daily = defaultdict(list)
    for r in rows('financial/data/prepaid_daily.csv'):
        daily[r['customer_id']].append({k:r[k] for k in ['date','usage_cost_cents','import_kwh','disconnected_hours','topup_cents']})
    snapshots = defaultdict(list)
    # Stream >600k intervals. Only completed 11:30 intervals form noon credit snapshots.
    with gzip.open(source/'financial/data/prepaid_intervals.csv.gz','rt') as f:
        for r in csv.DictReader(f):
            if r['interval_start'][11:19] == '11:30:00':
                snapshots[r['customer_id']].append([r['date'], int(r['closing_credit_cents']) + at_noon[(r['customer_id'], r['date'])]])
    data = {'version':selection['version'], 'customers':[], 'daily':daily, 'credit':snapshots,
            'rules':rules, 'topups':topups,
            'supply': rows('financial/data/prepaid_supply_events.csv'),
            'needs':rows('base/support_needs_history.csv')+rows('operations/data/scenario_needs_history.csv'),
            'arrangements':rows('base/support_arrangement_history.csv')+rows('operations/data/scenario_arrangement_history.csv'),
            'permissions':rows('base/contact_permission_history.csv'),
            'context':rows('public_context/horizon_12_context_join.csv'),
            'footprints':json.loads((source/'operations/hazard_footprints.geojson').read_text())}
    for c in customers:
        loc=locations[c['customer_id']]
        data['customers'].append({k:c[k] for k in ['customer_id','locality','region','postcode','account_open_date','account_close_date']} | {'longitude':float(loc['longitude']),'latitude':float(loc['latitude'])})
    tables={'forecasts':'weather_forecast_vintages','outlook':'seasonal_planning_outlook','capacity':'annual_capacity_planning','campaigns':'campaigns','audience':'campaign_audience','cases':'support_cases','contacts':'contact_attempts','offers':'assistance_offers','decisions':'offer_decisions','deliveries':'support_deliveries','resolutions':'need_resolutions'}
    for key, name in tables.items():
        data[key]=rows('operations/data/'+name+'.csv')
    # Remove cutoff summaries, inferred permissions and staff details from the UI payload.
    data['cases']=[{k:r[k] for k in ['case_id','customer_id','campaign_id','opened_at','need_id']} for r in data['cases']]
    data['audience']=[{k:r[k] for k in ['campaign_id','customer_id','geometry_id','eligibility_at']} for r in data['audience']]
    data['contacts']=[{k:r[k] for k in ['contact_id','case_id','campaign_id','customer_id','occurred_at','direction','channel','permission_history_id','outcome']} for r in data['contacts']]
    # Keep the eight-account financial override together; retain base finance only
    # for the remaining billed accounts. Never use bill paid-at-cutoff summaries.
    override={r['customer_id'] for r in rows('financial/data/postpaid_account_snapshot.csv')}
    cents=lambda value:int(Decimal(value)*100)
    data['billed_usage']=defaultdict(list)
    for name in ['base/consumption_daily.csv.gz','financial/data/postpaid_preserved_consumption.csv']:
        for r in rows(name):
            cid=r['customer_id']
            if cid in rules or not ('2025-01-01'<=r['date']<'2025-04-01'):continue
            if name.startswith('base/') and cid in override:continue
            data['billed_usage'][cid].append([r['date'],float(r['import_kwh'])])
    data['bills']=[];data['billed_payments']=[];data['billed_rules']={}
    for r in rows('base/bills.csv'):
        if r['customer_id'] in override or r['customer_id'] in rules or r['issue_date']>='2025-04-01':continue
        if r['is_opening_debt']=='True':continue
        data['bills'].append({'customer_id':r['customer_id'],'bill_id':r['bill_id'],'issue_date':r['issue_date'],'period_start':r['period_start_date'],'period_end':r['period_end_date'],'due_date':r['original_due_date'],'kwh':float(r['kwh']),'usage_charge_cents':cents(r['usage_charge']),'supply_charge_cents':cents(r['supply_charge']),'amount_due_cents':cents(r['amount_due']),'source':'base'})
    for r in rows('financial/data/postpaid_bills.csv'):
        data['bills'].append({k:r[k] for k in ['customer_id','bill_id','issue_date','period_start','period_end','due_date','kwh','usage_charge_cents','supply_charge_cents','amount_due_cents']}|{'source':'financial'})
    for r in rows('base/payments.csv'):
        if r['customer_id'] in override or r['customer_id'] in rules or r['date']>='2025-04-01':continue
        if r['kind']!='bill_payment':continue
        data['billed_payments'].append({'customer_id':r['customer_id'],'payment_id':r['payment_id'],'date':r['date'],'amount_cents':cents(r['amount']),'status':r['status'],'source':'base'})
    for r in rows('financial/data/postpaid_payments.csv'):
        data['billed_payments'].append({k:r[k] for k in ['customer_id','payment_id','date','amount_cents','status']}|{'source':'financial'})
    data['allocations']=rows('financial/data/postpaid_payment_allocations.csv')
    for c in customers:
        if c['customer_id'] in override:
            data['billed_rules'][c['customer_id']]={'usage_cents_per_kwh':33,'supply_cents_per_day':110,'concession_cents_per_day':70 if c['concession_card']=='True' else 0}
    # All numbers stay source-backed; no scores, simulator demand, realised hazard or base funnel.
    out.mkdir(parents=True,exist_ok=True)
    target=out/'scenario.json';target.write_text(json.dumps(data,separators=(',',':')))
    report={'source_archive':'TeamConnect-Complete-Synthetic-Demo-2025Q1-v1.zip','selection_manifest_sha256':hashlib.sha256((source/'selection_manifest.json').read_bytes()).hexdigest(),'release':selection['version'],'timezone':'AWST UTC+08:00','analysis_time':'selected date at 12:00 AWST','scenario_json_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size,'customers':len(customers),'prepaid_accounts':len(rules),'noon_credit_rows':sum(map(len,snapshots.values())),'source':'canonical selection_manifest.json; financial override + OP25 operations; union distinct need/arrangement episodes','excluded':['raw intervals','demand_kwh','requested_cost_cents','observed_magnitude','customer_event_exposure','full-window case status','old model outputs','base financial overrides','base funnel']}
    (out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('release',type=Path);p.add_argument('--out',type=Path,default=Path('teamconnect'));a=p.parse_args();build(a.release,a.out)
