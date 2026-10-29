"""Pinned reviewed synthetic financial coverage; uploaded metadata cannot expand it."""
from functools import lru_cache
from pathlib import Path
import copy
from source_adapter import parse,require,digest

REGISTRY_PATH=Path(__file__).resolve().parents[1]/'data/financial/registry.json'
REGISTRY_SHA='e0ea0a6d28d0cb154ee8f876601170ff9243fb562e0dcf692e287ce90aaa2fd4'

@lru_cache(maxsize=1)
def _registry():
    with REGISTRY_PATH.open('rb') as f:raw=f.read(256*1024+1)
    require(len(raw)<=256*1024 and digest(raw)==REGISTRY_SHA,'financial_registry_integrity')
    d=parse(raw.decode('utf-8'));require(type(d) is dict and d.get('schemaVersion')==1 and type(d.get('fixtures')) is dict,'financial_registry_contract')
    return d

def reviewed_entry(manifest_hash):
    require(type(manifest_hash) is str and manifest_hash in _registry()['fixtures'],'unreviewed_financial_manifest')
    return copy.deepcopy(_registry()['fixtures'][manifest_hash])
