"""Thin, read-only adapters for the existing candidate business CSVs."""
from __future__ import annotations
import csv
import os
import gzip
import hashlib
import json
import math
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path
from .work import checkpoint

DEFAULT_SOURCE=Path(os.environ.get('Q1_SOURCE_DIR', Path(__file__).resolve().parents[1]/'data/input-pack'))
KEYS={'customers':('customer_id',),'customer_locations':('customer_id',),'consumption_daily':('customer_id','date'),'prepay_daily':('customer_id','date'),'prepay_topups':('customer_id','datetime'),'bills':('bill_id',),'payments':('payment_id',),'support_needs_history':('history_id',),'support_arrangement_history':('history_id',),'hardship_programs':('hardship_id',),'hugs_grants':('hugs_id',),'payment_arrangements':('arrangement_id',)}
NUMBERS={
 'consumption_daily':('import_kwh','import_peak_kwh','import_offpeak_kwh','import_superoffpeak_kwh','export_kwh','outage_hours'),
 'prepay_daily':('opening_credit','topup_amount','usage_cost','closing_credit','unfunded_recorded_cost'),
 'prepay_topups':('amount',),'bills':('kwh','usage_charge','supply_charge','feed_in_credit','concession_credit','govt_bill_credit','amount_due'),
 'payments':('amount',),'hardship_programs':('debt_at_entry','instalment','debt_at_exit','write_off'),
 'hugs_grants':('debt_at_application','grant_amount','region_cap'),'payment_arrangements':('amount','instalment','n_instalments'),
}

class InputError(ValueError):
    """An input contract violation, never a zero-valued observation."""

class _NonCanonicalDate(ValueError):pass

def number(value, *, field, required=False, nonnegative=False):
    if value in ('',None):
        if required: raise InputError(f'{field}: missing required number')
        return None
    try: result=float(value)
    except (ValueError,TypeError) as exc: raise InputError(f'{field}: invalid number') from exc
    if not math.isfinite(result): raise InputError(f'{field}: non-finite number')
    if nonnegative and result<0: raise InputError(f'{field}: negative value')
    return result

@lru_cache(maxsize=4096)
def _canonical_date(value):
    parsed=date.fromisoformat(value)
    if parsed.isoformat()!=value:raise _NonCanonicalDate()
    return parsed

@lru_cache(maxsize=64)
def _date_fields(headers):
    return tuple(field for field in headers if field.endswith('_date') or field in ('date','effective_from','effective_to'))

def iso(value, *, field, required=False):
    if not value:
        if required: raise InputError(f'{field}: missing required date')
        return None
    try: parsed=_canonical_date(value)
    except _NonCanonicalDate as exc:raise InputError(f'{field}: date is not canonical') from exc
    except (ValueError,TypeError) as exc: raise InputError(f'{field}: invalid ISO date') from exc
    return parsed

def validate_row(name,row,known):
    if row['customer_id'] not in known: raise InputError(f'{name}: unknown customer_id')
    for field in NUMBERS.get(name,()):
        value=number(row[field],field=f'{name}.{field}',required=name in ('consumption_daily','prepay_daily'))
        if name in ('consumption_daily','prepay_daily') and value is not None and value<0:
            raise InputError(f'{name}.{field}: negative value')
    for field in _date_fields(tuple(row)):
        if row[field]:iso(row[field],field=f'{name}.{field}')
    if name=='customers':
        if row['prepayment_meter'] not in ('True','False'): raise InputError('customers.prepayment_meter: expected True or False')
        opened=iso(row['account_open_date'],field='customers.account_open_date',required=True)
        closed=iso(row['account_close_date'],field='customers.account_close_date')
        if closed and closed<opened: raise InputError('customers: closure precedes opening')
    if name=='consumption_daily':
        if row['supply_status'] not in ('connected','disconnected_non_payment'): raise InputError('consumption_daily: unsupported supply status')
        if float(row['outage_hours'])>24: raise InputError('consumption_daily: outage hours exceed 24')
        parts=sum(float(row[k]) for k in ('import_peak_kwh','import_offpeak_kwh','import_superoffpeak_kwh'))
        if abs(parts-float(row['import_kwh']))>0.0031: raise InputError('consumption_daily: import components do not reconcile')
    if name=='prepay_daily':
        available=float(row['opening_credit'])+float(row['topup_amount'])
        closing=max(0,available-float(row['usage_cost']))
        gap=max(0,float(row['usage_cost'])-available)
        if abs(closing-float(row['closing_credit']))>0.021 or abs(gap-float(row['unfunded_recorded_cost']))>0.021:
            raise InputError('prepay_daily: credit/usage ledger does not reconcile')

def load_business(root=DEFAULT_SOURCE, *, postcode='6765', verify_hashes=True):
    root=Path(root)
    manifest=json.loads((root/'SCHEMAS-AND-COVERAGE.json').read_text())
    specs=manifest['files']; tables={}; audit=[]; known=set(); selected=set()
    for spec in specs:
        checkpoint()
        path=root/spec['file']; name=path.name.replace('.csv.gz','').replace('.csv','')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        checkpoint()
        if verify_hashes and digest!=spec['sha256']: raise InputError(f'{name}: source hash mismatch')
        op=gzip.open if path.suffix=='.gz' else open
        seen=set(); retained=[]; count=0
        with op(path,'rt',newline='',encoding='utf-8-sig') as stream:
            reader=csv.DictReader(stream)
            if reader.fieldnames!=spec['headers']: raise InputError(f'{name}: source headers changed')
            for row in reader:
                checkpoint()
                count+=1
                if None in row or any(v is None for v in row.values()): raise InputError(f'{name}: malformed CSV row {count}')
                key=tuple(row[k] for k in KEYS[name])
                if any(not x for x in key) or key in seen: raise InputError(f'{name}: duplicate or blank key at row {count}')
                seen.add(key)
                if name=='customers':
                    known.add(row['customer_id'])
                    if row['postcode']==postcode: selected.add(row['customer_id'])
                validate_row(name,row,known)
                if row['customer_id'] in selected: retained.append(row)
        if count!=spec['rows']: raise InputError(f'{name}: row count differs from retained source manifest')
        tables[name]=retained
        audit.append({'file':spec['file'],'sha256':digest,'source_rows':count,'locality_rows':len(retained),'ordered_headers':spec['headers'],'key':list(KEYS[name])})
    # Existing history references must point to the original parent record and customer.
    parents={name:{r[field]:r['customer_id'] for r in tables[name]} for name,field in [('payment_arrangements','arrangement_id'),('hardship_programs','hardship_id')]}
    for row in tables['support_arrangement_history']:
        if parents.get(row['source_table'],{}).get(row['arrangement_id'])!=row['customer_id']:
            raise InputError('support_arrangement_history: parent arrangement/customer mismatch')
    return tables,{'source_version':manifest['source_version'],'synthetic_business':True,'postcode':postcode,'files':audit,'source_root':str(root)}
