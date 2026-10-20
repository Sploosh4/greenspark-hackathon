"""Build a deterministic UI scenario. Alerts and forecasts are illustrative, not analysis."""
import argparse, csv, io, json, pathlib, random, zipfile

ROOT = pathlib.Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--data-zip', type=pathlib.Path, default=ROOT/'data'/'mock-data.zip', help='Original archive (default: data/mock-data.zip beside this script).')
args = parser.parse_args()
rng = random.Random(318)
with zipfile.ZipFile(args.data_zip) as archive:
    customers = list(csv.DictReader(io.StringIO(archive.read('customers.csv').decode())))
    preferences = {r['customer_id']: r for r in csv.DictReader(io.StringIO(archive.read('contact_preferences.csv').decode()))}

extensions = [
    {'id':'heat','label':'Heatwave credit','short':'Credit shortfall','icon':'sun','color':'#c88f59'},
    {'id':'usage','label':'Usage changes','short':'Usage change','icon':'activity','color':'#559e8e'},
    {'id':'bill','label':'Bill pressure','short':'Bill increase','icon':'receipt','color':'#9580b9'},
    {'id':'outage','label':'Outage readiness','short':'Planned outage','icon':'bolt','color':'#8098ba'},
    {'id':'solar','label':'Solar performance','short':'Solar exports','icon':'solar','color':'#bca061'}
]
prepay = [c for c in customers if c['prepayment_meter'] == 'True']
billed = [c for c in customers if c['prepayment_meter'] == 'False']
solar = [c for c in billed if c['has_solar'] == 'True']
for cohort in [prepay,billed,solar]: rng.shuffle(cohort)
heat_people = sorted(prepay, key=lambda c: preferences[c['customer_id']]['consent_proactive_support_contact'] != 'yes')[:10] + prepay[30:48]
seen=set()
heat_people=[c for c in heat_people if not (c['customer_id'] in seen or seen.add(c['customer_id']))]
for c in prepay:
    if len(heat_people)>=28: break
    if c['customer_id'] not in seen: heat_people.append(c);seen.add(c['customer_id'])
solar_people = [c for c in solar if c['retailer']=='Synergy'][:17] + [c for c in solar if c['retailer']=='Horizon Power'][:2]
groups = {'heat':heat_people,'usage':prepay[50:60]+billed[10:64],'bill':billed[100:212],'outage':prepay[70:77]+billed[300:336],'solar':solar_people}
cases=[]
for ext, people in groups.items():
    for i,c in enumerate(people):
        p=preferences[c['customer_id']]
        consent=p['consent_proactive_support_contact']
        channels=[]
        if p['sms_opt_in']=='True':channels.append('SMS')
        if p['email_opt_in']=='True':channels.append('Email')
        if p['do_not_call']=='False':channels.append('Phone')
        preferred={'sms':'SMS','email':'Email','phone':'Phone','post':'Post'}[p['preferred_channel']]
        channel=preferred if preferred in channels else (channels[0] if channels else 'Review')
        r={'id':f'GS-{len(cases)+1001}','customer':c['customer_id'],'retailer':c['retailer'],'region':c['region'],'locality':c['locality'],'postcode':c['postcode'],'prepay':c['prepayment_meter']=='True','lifeSupport':c['life_support']=='True','interpreter':c['interpreter_required']=='True','consent':consent,'channel':channel,'preferred':preferred,'smsOptIn':p['sms_opt_in']=='True','emailOptIn':p['email_opt_in']=='True','doNotCall':p['do_not_call']=='True','eligible':consent=='yes' and bool(channels),'extension':ext,'dueDay':i%7,'status':'Open'}
        if ext=='heat':
            r.update(credit=round(rng.uniform(4,32),2),dailyCost=round(rng.uniform(6,13),2),temperature=rng.choice([40,41,42,43]))
            r['hours']=round(r['credit']/r['dailyCost']*24)
            r['dueDay']=min(6,r['hours']//24)
            r['priority']='Urgent' if r['hours']<24 else 'High' if r['hours']<48 else 'Review'
            r['detail']=f"{r['hours']}h credit · {r['temperature']}°C"
            r['fields']=[['Credit',f"${r['credit']:.2f}"],['Daily cost · est.',f"${r['dailyCost']:.2f}"],['Credit remaining · est.',f"{r['hours']}h"],['Forecast peak',f"{r['temperature']}°C"]]
        elif ext=='usage':
            r['change']=-rng.randint(32,84)
            r['context']='Self-disconnection' if i<8 else 'Outage overlap' if i<26 else 'Solar shift' if i<37 else 'Unexplained'
            r['priority']='Urgent' if r['context']=='Unexplained' and r['change']<-65 else 'High' if r['context'] in ['Unexplained','Self-disconnection'] else 'Review'
            r['detail']=f"{r['change']}% import · {r['context'].lower()}"
            r['fields']=[['Import change',f"{r['change']}%"],['Window','7 days'],['Context',r['context']],['Previous average',f"{rng.uniform(7,19):.1f} kWh/day"]]
        elif ext=='bill':
            r['usual']=rng.randrange(140,370,5);r['uplift']=rng.randint(25,65);r['forecast']=round(r['usual']*(1+r['uplift']/100))
            r['priority']='Urgent' if r['uplift']>=55 else 'High' if r['uplift']>=40 else 'Review'
            r['detail']=f"+{r['uplift']}% · ${r['forecast']} est."
            r['fields']=[['Usual bill',f"${r['usual']}"],['Forecast bill · est.',f"${r['forecast']}"],['Increase · est.',f"+{r['uplift']}%"],['Billing period','Jan–Feb 2025']]
        elif ext=='outage':
            r['duration']=rng.choice([3,4,5,6,8]);r['priority']='Urgent' if r['lifeSupport'] else 'High' if r['duration']>=6 else 'Review'
            r['detail']=f"{r['duration']}h · "+('Life support' if r['lifeSupport'] else 'Planned maintenance')
            r['fields']=[['Scheduled',f"{14+r['dueDay']} Jan · 08:00"],['Duration',f"{r['duration']} hours"],['Life support','Registered' if r['lifeSupport'] else 'No flag'],['Supply','Prepayment' if r['prepay'] else 'Billed']]
        else:
            r['exportChange']=-rng.randint(30,78);r['importChange']=rng.randint(23,82)
            r['priority']='High' if r['exportChange']<-55 else 'Review'
            r['detail']=f"{r['exportChange']}% export · +{r['importChange']}% import"
            r['fields']=[['Export change',f"{r['exportChange']}%"],['Import change',f"+{r['importChange']}%"],['Solar system',f"{c['solar_kw']} kW"],['Window','7 days']]
        r['history']=[rng.randint(12,70) for _ in range(14)]
        if ext=='solar':
            # Illustrative weather/season baselines; no live weather feed is in the archive.
            solar_rng=random.Random('solar-evidence:'+r['customer'])
            sindex=sum(x['extension']=='solar' and x['retailer']==r['retailer'] for x in cases)
            pattern=sindex%6
            r['cloudExplainsDrop']=pattern==1
            r['seasonExplainsDrop']=pattern==2
            r['expectedExportChange']=r['exportChange'] if pattern in [1,2] else -solar_rng.randint(3,12)
            r['sunnyDayShortfalls7d']=solar_rng.randint(3,5) if pattern in [0,4] else 0
            if pattern==3:r['importChange']=0  # A drop without corroboration stays out of the queue.
            if pattern==5:r['expectedExportChange']=r['exportChange']+5  # Small residual after adjustment.
            r.pop('priority',None)
            r['fields']=[['Export change · 7d',f"{r['exportChange']}%"],['Import change · 7d',f"+{r['importChange']}%"],['Expected export change · adjusted',f"{r['expectedExportChange']}%"],['Solar system',f"{c['solar_kw']} kW"],['Cloud explanation','Matched' if r['cloudExplainsDrop'] else 'No match'],['Seasonal explanation','Matched' if r['seasonExplainsDrop'] else 'No match'],['Sunny-day shortfalls · 7d',str(r['sunnyDayShortfalls7d'])],['Window','7 days']]
        if ext=='usage':
            usage_rng=random.Random('usage-evidence:'+r['customer'])
            r['outageExplainsDrop']=r['context']=='Outage overlap'
            r['solarExplainsDrop']=r['context']=='Solar shift'
            r['selfDisconnections7d']=usage_rng.randint(1,3) if r['context']=='Self-disconnection' else 0
            r['nearZeroUsageDays7d']=0
            r['hotDays7d']=0
            r['hotDayUsageChange']=None
            r['declineDays']=1
            if r['context']=='Unexplained':
                uindex=sum(x['extension']=='usage' and x['context']=='Unexplained' and x['retailer']==r['retailer'] for x in cases)
                pattern=uindex%6
                if pattern in [1,4,5]:r['declineDays']=usage_rng.randint(3,7)
                if pattern in [2,4]:r['nearZeroUsageDays7d']=usage_rng.randint(2,4)
                if pattern in [3,5]:
                    r['hotDays7d']=usage_rng.randint(2,4)
                    r['hotDayUsageChange']=-usage_rng.randint(35,80)
            elif r['context'] in ['Outage overlap','Solar shift']:
                r['declineDays']=5
                r['nearZeroUsageDays7d']=3
            r.pop('priority',None)
            r['fields'] += [['Outage explanation','Matched' if r['outageExplainsDrop'] else 'No match'],['Solar explanation','Matched' if r['solarExplainsDrop'] else 'No match'],['Self-disconnections · 7d',str(r['selfDisconnections7d'])],['Near-zero use · 7d',f"{r['nearZeroUsageDays7d']} days"],['Decline duration',f"{r['declineDays']} days"],['Hot days · 7d',str(r['hotDays7d'])]]
            if r['hotDayUsageChange'] is not None:r['fields'].append(['Hot-day usage change',f"{r['hotDayUsageChange']}%"])
        if ext=='bill':
            # Payment stress is a separate, deterministic scenario; it does not alter other fixtures.
            retailer_index=sum(x['extension']=='bill' and x['retailer']==r['retailer'] for x in cases)
            pattern=retailer_index%8
            stress_rng=random.Random('bill-stress:'+r['customer'])
            r['missedPayments90d']=stress_rng.randint(1,3) if pattern in [1,4,5,7] else 0
            r['failedDirectDebits90d']=stress_rng.randint(1,2) if pattern in [2,4,6,7] else 0
            r['arrearsPrevious']=stress_rng.randrange(0,360,20)
            r['arrearsCurrent']=r['arrearsPrevious']+stress_rng.randrange(80,420,20) if pattern in [3,5,6,7] else max(0,r['arrearsPrevious']-40)
            r.pop('priority',None)  # Computed by the browser's shared bill-pressure rules.
            r['fields'] += [['Missed payments · 90d',str(r['missedPayments90d'])],['Failed direct debits · 90d',str(r['failedDirectDebits90d'])],['Arrears · 30 Nov',f"${r['arrearsPrevious']}"],['Arrears · 31 Dec',f"${r['arrearsCurrent']}"]]
        cases.append(r)

payload={'meta':{'classification':'illustrative-ui-scenario','date':'2025-01-14','timezone':'Australia/Perth','source':'mock-data.zip','sourceScope':'Customer IDs, retailer, region, account characteristics and contact preferences. All alerts, forecast weather, financial estimates, missed payments, failed direct debits, arrears history, usage-context assessments, usage-supporting indicators, solar weather/season assessments, adjusted export baselines, sunny-day shortfalls, queue states and time series are simulated.','notLive':True},'extensions':extensions,'population':[{'retailer':c['retailer'],'region':c['region'],'prepay':c['prepayment_meter']=='True'} for c in customers],'cases':cases,'forecast':{'All regions':[39,41,43,42,40,38,36],'Perth metro':[34,36,38,39,37,34,32],'Pilbara':[40,42,43,42,41,39,38],'Kimberley':[36,37,39,40,39,38,37],'Gascoyne':[39,40,42,41,39,38,36]}}
(ROOT/'dist'/'data.json').write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8')
print(json.dumps({'cases':len(cases),'byExtension':{k:len(v) for k,v in groups.items()},'population':len(customers)}))
