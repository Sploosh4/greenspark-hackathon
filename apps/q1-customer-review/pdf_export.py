"""Local selected-customer PDF renderer. No source reads, fitting or network."""
from io import BytesIO
from datetime import date
from statistics import fmean
from math import isfinite
from pathlib import Path
from xml.sax.saxutils import escape
import json
import sys
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4,landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

GREEN='#176344'
INK='#243438'
FONT=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
pdfmetrics.registerFont(TTFont('Review',str(FONT)))
BODY=ParagraphStyle('Body',fontName='Review',fontSize=9,leading=14,textColor=HexColor(INK),spaceAfter=8,splitLongWords=True)
SMALL=ParagraphStyle('Small',parent=BODY,fontSize=8,leading=12,textColor=HexColor('#536568'))
TITLE=ParagraphStyle('Title',parent=BODY,fontSize=19,leading=25,spaceAfter=8)
HEAD=ParagraphStyle('Heading',parent=BODY,fontSize=11,leading=16,spaceBefore=14,spaceAfter=7,keepWithNext=False)

def p(value,style=BODY):
    return Paragraph(escape(str(value if value is not None else 'Unavailable')).replace('\n','<br/>'),style)

def number(value,unit='',digits=1):
    if value is None:return 'Unavailable'
    value=float(value)
    return f'{value:,.{digits}f}{unit}' if isfinite(value) else 'Unavailable'

def percent(value):
    return 'Unavailable' if value is None else f'{float(value):+.1f}%'.replace('+0.0%','0.0%')

def cash(value):return 'Unavailable' if value in (None,'') else f'${float(value):,.2f}'

def estimates(row,review):
    calculated=isinstance(row.get('predictions'),list)
    if calculated: mapping={e['event_id']:e for e in row['predictions']}
    else:
        recent=[float(r['import_kwh']) for r in row['usage'] if '2024-12-19'<=r['date']<=review['history_cutoff']]
        baseline=fmean(recent) if len(recent)==14 else None
    result=[]
    for i,event in enumerate(review['events']):
        duration=(date.fromisoformat(event['end'])-date.fromisoformat(event['start'])).days+1
        if calculated: estimate=mapping.get(event['id'],{})
        else:
            increase=row['expected_percent_fixture'][i]
            estimate={'baseline':baseline,'increase':increase,'predicted':None if increase is None or baseline is None else baseline*(1+increase/100)}
        result.append({**event,**estimate,'duration':duration})
    return result

def table(headers,rows,widths):
    cells=[[p(h,SMALL) for h in headers]]
    for row in rows:
        cells.append([v if isinstance(v,Paragraph) else p(v) for v in row])
    t=LongTable(cells,colWidths=widths,repeatRows=1,hAlign='LEFT',splitByRow=1,splitInRow=1)
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),HexColor('#edf3f2')),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('LINEBELOW',(0,0),(-1,0),.5,HexColor('#cfddda')),
        ('LINEBELOW',(0,1),(-1,-1),.3,HexColor('#e4ecea')),
    ]))
    return t

def create_summary(review,customer_ids):
    if not isinstance(customer_ids,list) or not 1<=len(customer_ids)<=100 or any(not isinstance(c,str) for c in customer_ids):
        raise ValueError('Select between 1 and 100 customers')
    ids=list(dict.fromkeys(customer_ids))
    customers={r['customer']['customer_id']:r for r in review['customers']}
    if any(c not in customers for c in ids):raise ValueError('Selected customer is unavailable in this data mode')
    out=BytesIO(); width=A4[0]-88
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=44,rightMargin=44,topMargin=62,bottomMargin=48,title='Q1 selected customer summary',author='Team Connect')
    story=[]
    for i,cid in enumerate(ids):
        if i:story.append(PageBreak())
        row=customers[cid];c=row['customer'];es=estimates(row,review)
        story.extend([p(cid,TITLE),p(f"{'Prepaid' if c['prepayment_meter']=='True' else 'Billed'} | {c['locality']} {c['postcode']} | Review {review['review_date']}",SMALL)])
        if review.get('batch_revision'):story.append(p('Data version: '+review['batch_revision']+' | '+review.get('data_mode','demo'),SMALL))
        if review.get('replay') or review.get('current_demo'):story.append(p(('Current-date synthetic scenario | frozen M5 v3 | S1 comparison | ' if review.get('current_demo') else 'Simulated historical replay | synthetic accounts | frozen M5 v3 | S1 comparison | ')+(review.get('current_demo') or review['replay'])['denominator_policy'],SMALL))
        if review.get('current_demo'):story.append(p('Current-date synthetic scenario | reported usage through '+str(row.get('latest_reported_usage_date'))+' | reporting lag '+str(row.get('reporting_lag_days'))+' days | forecast retrieved '+str(review['current_demo'].get('weather_retrieved_at'))+' | provider issue unknown',SMALL))
        if not row['financial']:
            story.append(p('No prepaid balance records were supplied.' if c['prepayment_meter']=='True' else 'No bill records were supplied. The amount owed cannot be checked from this data.'))
        story.append(p('Electricity estimates',HEAD))
        story.append(table(['Scenario' if review.get('current_demo') else 'Heat period','Days','Daily grid use','Change','Event total'],[
            [f"{e['label']}\n{e['start']} to {e['end']}",str(e['duration']),number(e.get('predicted'),' kWh'),percent(e.get('increase')),number(None if e.get('predicted') is None else e['predicted']*e['duration'],' kWh')]
            for e in es
        ] or [['No heat period in the review window','-','Unavailable','Unavailable','Unavailable']], [width*.34,width*.08,width*.20,width*.18,width*.20]))
        baselines=list(dict.fromkeys(number(e.get('baseline'),' kWh/day') for e in es))
        if baselines:story.append(p('Recent daily grid use: '+', '.join(baselines),SMALL))
        if review.get('replay') or review.get('current_demo'):
            for e in es:
                comparison=e.get('comparison',{})
                story.append(p('Simple baseline (S1), '+e['start']+' to '+e['end']+': '+number(comparison.get('predicted'),' kWh/day')+' | '+percent(comparison.get('increase')),SMALL))
        story.append(p('Past heat-linked comparison',HEAD))
        episodes=[e for e in row['episodes'] if e.get('linked') and e['start']>=review['history_window_start'] and e['end']<=review['history_cutoff']]
        story.append(table(['Period','Recorded context','Change in daily grid use'],[
            [e['start']+' to '+e['end'],e['label'],percent(e.get('increase_percent'))+(('\n'+number(e.get('actual_mean'),' kWh/day observed',2)+'\n'+number(e.get('denominator'),' kWh/day baseline',2)+'\n'+str(e.get('baseline_support',{}).get('n',0))+' reported baseline days') if review.get('replay') or review.get('current_demo') else '')] for e in episodes
        ] or [['No linked comparison available','Unlinked help is excluded','Unavailable']], [width*.28,width*.49,width*.23]))
        story.append(p('Shared account facts',HEAD));facts=[]
        for r in row['financial']:facts.append([r['kind'],r['date'],cash(r.get('amount'))])
        for r in row['records']:
            label=p(r['kind'])
            if r['kind']=='Payment recorded':label=Paragraph('<font color="'+GREEN+'">&#10003; Payment recorded</font>',BODY)
            facts.append([label,r['date'],r['id']])
        story.append(table(['Record','Date','Amount / reference'],facts or [['No account facts supplied','-','Unavailable']], [width*.35,width*.21,width*.44]))
        story.append(Spacer(1,12))
        calculated=review.get('kind')=='calculated_historical_replay'
        provenance='Historical replay | synthetic accounts | unvalidated usage estimate.' if calculated else 'Historical UI fixture | synthetic accounts | example estimates.'
        if review.get('replay') or review.get('current_demo'):provenance='Simulated historical replay | original availability unknown | historical oracle weather. Model manifest: '+(review.get('current_demo') or review['replay'])['model_manifest_sha256']+'.'
        if calculated:provenance+=' Method: '+review['method']['id']+'.'
        if review.get('current_demo'):provenance='Current-date synthetic demo | modelled weather inputs | current accuracy unvalidated | original row availability unknown.'
        story.append(p(provenance,SMALL))
    def page_footer(canv,document):
        canv.setFont('Review',8);canv.setFillColor(HexColor('#536568'))
        canv.drawString(44,A4[1]-35,'Team Connect | Customer review')
        canv.drawString(44,28,'Selected customers: '+str(len(ids)))
        canv.drawRightString(A4[0]-44,28,'Page '+str(document.page))
    class StableCanvas(canvas.Canvas):
        def __init__(self,*args,**kwargs):kwargs['invariant']=1;super().__init__(*args,**kwargs)
    doc.build(story,onFirstPage=page_footer,onLaterPages=page_footer,canvasmaker=StableCanvas)
    return out.getvalue()

def create_condensed_summary(review,customer_ids):
    """One customer row; event estimates stay separate within its cells."""
    if not isinstance(customer_ids,list) or not 1<=len(customer_ids)<=100 or any(not isinstance(c,str) for c in customer_ids):raise ValueError('Select between1and100customers')
    ids=list(dict.fromkeys(customer_ids));mapping={r['customer']['customer_id']:r for r in review['customers']}
    if any(cid not in mapping for cid in ids):raise ValueError('Selected customer is unavailable in this data mode')
    compact=ParagraphStyle('Compact',parent=BODY,fontSize=7.5,leading=10,spaceAfter=2)
    output=BytesIO();page=landscape(A4);width=page[0]-88
    doc=SimpleDocTemplate(output,pagesize=page,leftMargin=44,rightMargin=44,topMargin=44,bottomMargin=38,title='Q1 condensed customer summary',author='Team Connect')
    caption='Synthetic performance fixture | ' if review.get('performance_fixture') else 'Current-date synthetic scenario | ' if review.get('current_demo') else 'Historical replay | synthetic accounts | '
    story=[p('Selected customer summary',TITLE),p(caption+'Review '+review['review_date']+' | '+str(len(ids))+' customers | Data version '+review.get('batch_revision','unversioned'),SMALL)]
    if review.get('replay') or review.get('current_demo'):story.append(p(('Current-date synthetic scenario | M5 v3 with S1 comparison | ' if review.get('current_demo') else 'Simulated historical replay | M5 v3 with S1 comparison | ')+(review.get('current_demo') or review['replay'])['denominator_policy'],SMALL))
    if review.get('current_demo'):
        meta=review['current_demo'];story.append(p('Reporting lag: '+('/'.join(map(str,meta['reporting_lag_days'])) or 'unknown')+' days | forecast retrieved '+str(meta.get('weather_retrieved_at'))+' | provider issue unknown',SMALL))
    headings=['Customer','Account','Scenario' if review.get('current_demo') else 'Heat periods','Daily grid use\nusual / estimate','Change','Event total','Latest dated records']
    cells=[[p(value,compact) for value in headings]]
    for cid in ids:
        row=mapping[cid];customer=row['customer'];events=estimates(row,review)
        facts=[]
        if row['financial']:
            record=row['financial'][-1];facts.append(record['kind']+': '+cash(record.get('amount'))+' | '+record['date'])
        else:facts.append('No prepaid balance records supplied' if customer['prepayment_meter']=='True' else 'No bill records supplied; amount owed unavailable')
        for payments in (True,False):
            records=[r for r in row['records'] if (r['kind']=='Payment recorded')==payments]
            if records:
                record=max(records,key=lambda r:(r['date'],r['id']));facts.append(record['kind']+' | '+record['date']+' | '+record['id'])
        values=[cid,'Prepaid' if customer['prepayment_meter']=='True' else 'Billed',
          '\n'.join(e['start']+' to '+e['end']+' ('+str(e['duration'])+' days)' for e in events) or 'No heat period in this replay',
          '\n'.join(number(e.get('baseline'))+' / '+number(e.get('predicted'),' kWh')+(('\nS1: '+number(e.get('comparison',{}).get('predicted'),' kWh')) if review.get('replay') or review.get('current_demo') else '') for e in events) or 'Unavailable',
          '\n'.join(percent(e.get('increase')) for e in events) or 'Unavailable',
          '\n'.join(number(None if e.get('predicted') is None else e['predicted']*e['duration'],' kWh') for e in events) or 'Unavailable',
          '\n'.join(facts)]
        rendered=[p(value,compact) for value in values]
        rendered[-1]=Paragraph('<br/>'.join('<font color="'+GREEN+'">'+escape(fact)+'</font>' if fact.startswith('Payment recorded') else escape(fact) for fact in facts),compact)
        cells.append(rendered)
    table=LongTable(cells,colWidths=[width*f for f in (.13,.08,.22,.12,.09,.11,.25)],repeatRows=1,hAlign='LEFT',splitByRow=1,splitInRow=1)
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),HexColor('#eef4f2')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,-1),.3,HexColor('#dce6e2'))]))
    provenance='Synthetic performance fixture | authored estimates | no prediction-quality claim.' if review.get('performance_fixture') else 'Historical replay | synthetic business | unvalidated estimate.'
    if review.get('replay') or review.get('current_demo'):provenance='Simulated historical replay | synthetic accounts | original availability unknown | historical oracle weather.'
    if review.get('current_demo'):provenance='Current-date synthetic demo | external modelled weather | current accuracy unvalidated.'
    story.extend([table,Spacer(1,10),p(provenance+' Latest dated records only; individual customer summaries retain the full supplied account history.',SMALL)])
    def footer(canv,document):
        canv.setFont('Review',7);canv.setFillColor(HexColor('#536568'));canv.drawString(44,23,'Team Connect Q1 | '+review.get('batch_revision','unversioned'));canv.drawRightString(page[0]-44,23,'Page '+str(document.page))
    class StableCanvas(canvas.Canvas):
        def __init__(self,*args,**kwargs):kwargs['invariant']=1;super().__init__(*args,**kwargs)
    doc.build(story,onFirstPage=footer,onLaterPages=footer,canvasmaker=StableCanvas);return output.getvalue()

if __name__=='__main__':
    payload=json.load(sys.stdin)
    renderer=create_condensed_summary if payload.get('format')=='condensed' else create_summary
    sys.stdout.buffer.write(renderer(payload['review'],payload['customer_ids']))
