"""Separate, bounded financial intake. Raw inputs never enter the saved snapshot."""
import copy,secrets,threading,re
from datetime import timedelta
from source_adapter import SourceError,require,canonical,digest,parse
from financial_support import HEADERS,derive_support_context
from financial_reference import reviewed_entry

MAX_FINANCIAL_UPLOAD=32*1024*1024
PART_FILES={'customers':'customers.csv','usage':'consumption_daily.csv.gz','manifest':'manifest.json','arrangements':'payment_arrangements.csv.gz','hardship':'hardship_programs.csv.gz','grants':'hugs_grants.csv.gz','support':'support_arrangement_history.csv.gz','payments':'payments.csv.gz'}
AREA_KEYS={'postcode','snapshotDate','activeAccountDenominator','activePaymentArrangementAccounts','activeHardshipProgramAccounts','activeAccountsInEitherSupport','paidGrantRecipientsInPeriod','paidGrantRecipientsActiveAtSnapshot','paidGrantCountInPeriod','paidGrantAmountCentsInPeriod'}
SUPPORT_KEYS={'schemaVersion','contract','historyStart','historyEnd','coverage','state','snapshotDate','classification','cohortCustomerSha256','cohortUsageSha256','reviewedManifestSha256','sourceHashes','areas','monthlyGrantLedger','definitions'}

def validate_attachment(s,business,entry=None):
    require(type(s) is dict and set(s)==SUPPORT_KEYS and type(s.get('schemaVersion')) is int and s['schemaVersion']==2 and s.get('contract')=='q3-financial-support-v2' and s.get('state')=='validated','financial_attachment_contract')
    entry=entry or reviewed_entry(s.get('reviewedManifestSha256'))
    require(s.get('snapshotDate')==business['snapshotDate']==entry['snapshotDate'] and s.get('historyStart')==business['historyStart']==entry['historyStart'] and s.get('historyEnd')==business['historyEnd']==entry['historyEnd'],'financial_snapshot_mismatch')
    require(s.get('cohortCustomerSha256')==business['customerSourceSha256']==entry['customerSourceSha256'] and s.get('cohortUsageSha256')==business['usageSourceSha256']==entry['usageSourceSha256'],'financial_cohort_mismatch')
    require(business.get('geographyRegistrySha256')==entry.get('geographyRegistrySha256'),'financial_geography_mismatch')
    coverage=s.get('coverage',{});pcs=sorted(a['postcode'] for a in business['areas'])
    require(coverage.get('accountPostcodes')==pcs==entry['accountPostcodes'] and coverage.get('completeTables')==sorted(HEADERS),'financial_coverage_mismatch')
    require(digest(canonical(s))==entry['aggregateSha256'],'financial_aggregate_integrity')
    areas=s.get('areas');require(type(areas) is list and [a.get('postcode') for a in areas]==pcs,'financial_area_coverage')
    known={a['postcode']:a for a in business['areas']}
    for a in areas:
        require(type(a) is dict and set(a)==AREA_KEYS,'financial_area_schema')
        require(a['snapshotDate']==business['snapshotDate'] and a['activeAccountDenominator']==known[a['postcode']]['accountCount'],'financial_area_denominator')
        keys=AREA_KEYS-{'postcode','snapshotDate'};require(all(type(a[k]) is int and 0<=a[k]<=9007199254740991 for k in keys),'financial_count_or_amount_invalid')
        n=a['activeAccountDenominator'];p=a['activePaymentArrangementAccounts'];h=a['activeHardshipProgramAccounts'];u=a['activeAccountsInEitherSupport']
        require(max(p,h)<=u<=min(n,p+h),'financial_support_union_invalid')
        require(a['paidGrantRecipientsActiveAtSnapshot']<=min(n,a['paidGrantRecipientsInPeriod']) and a['paidGrantRecipientsInPeriod']<=known[a['postcode']]['retainedAccountCount'] and a['paidGrantRecipientsInPeriod']<=a['paidGrantCountInPeriod'],'financial_grant_counts_invalid')
    return s

class FinancialStages:
    """Aggregate-only proposals bound to the account/source generation reviewed."""
    def __init__(self,store,trusted,clock,entry_lookup=reviewed_entry):
        self.store=store;self.trusted=trusted;self.clock=clock;self.lookup=entry_lookup;self.lock=threading.RLock();self.stages={}
    def _expire(self):
        self.stages={k:v for k,v in self.stages.items() if self.clock()<v['expires']}
    def stage(self,files,declared,expected_generation):
        require(declared is True,'synthetic_declaration_required')
        require(self.trusted is not None,'trusted_upload_context_unavailable')
        require(type(files) is dict and set(files)==set(PART_FILES),'complete_financial_upload_required')
        require(all(type(v) is bytes for v in files.values()) and 0<sum(len(v) for v in files.values())<=MAX_FINANCIAL_UPLOAD,'financial_upload_size_limit')
        require(len(files['manifest'])<=2*1024*1024,'financial_manifest_size')
        current=self.store.read();require(current['data'] is not None and not current['status']['last_refresh_error'],'current_source_unavailable')
        require(current['generation']==expected_generation,'active_snapshot_changed_restage_required')
        business=current['data']['business'];entry=self.lookup(digest(files['manifest']))
        try:metadata=parse(files['manifest'].decode('utf-8'))
        except UnicodeError:raise SourceError('financial_manifest_encoding') from None
        parameters=metadata.get('parameters',{})
        require(parameters.get('start')==entry['historyStart']==business['historyStart'] and parameters.get('end')==entry['historyEnd']==business['historyEnd'] and type(parameters.get('count')) is int and parameters['count']==business['retainedTotalAccounts']==entry['retainedAccounts'],'financial_manifest_window_or_cohort')
        require(entry['customerSourceSha256']==digest(files['customers'])==business['customerSourceSha256'] and entry['usageSourceSha256']==digest(files['usage'])==business['usageSourceSha256'],'financial_cohort_mismatch')
        sidecars={PART_FILES[k]:v for k,v in files.items() if k not in {'customers','usage','manifest'}}
        support=derive_support_context(files['customers'],files['usage'],True,self.trusted,self.clock().date(),business,sidecars,files['manifest'],digest(files['manifest']))
        validate_attachment(support,business,entry)
        # A concurrent business or climate commit invalidates the reviewed proposal.
        require(self.store.read()['generation']==current['generation'],'active_snapshot_changed_restage_required')
        with self.lock:
            self._expire();require(len(self.stages)<4,'too_many_staged_uploads')
            token=secrets.token_urlsafe(24);expires=self.clock()+timedelta(minutes=30)
            public={'stageId':token,'baseGeneration':current['generation'],'expiresAt':expires.isoformat(),'proposedSupport':support,'snapshotDate':support['snapshotDate'],'areaCount':len(support['areas']),'validation':{'rawRowsPersisted':False,'reviewedManifestSha256':support['reviewedManifestSha256'],'allRequiredTablesValidated':True,'accountCoverageMatched':True}}
            self.stages[token]={'public':public,'expires':expires,'base':current['generation'],'support':support}
            return copy.deepcopy(public)
    def replace(self,token,generation):
        with self.lock:
            self._expire();s=self.stages.get(token);require(s is not None,'stage_missing_or_expired');require(generation==s['base'],'staged_generation_mismatch')
            result=self.store.replace_financial_support(s['support'],generation)
            del self.stages[token];return result
    def discard(self,token):
        with self.lock:self.stages.pop(token,None)

from business_upload import UploadJobs
class FinancialJobs(UploadJobs):
    def submit(self,files,declared,expected_generation):
        require(declared is True,'synthetic_declaration_required')
        require(self.stages.trusted is not None,'trusted_upload_context_unavailable')
        require(type(files) is dict and set(files)==set(PART_FILES) and all(type(v) is bytes for v in files.values()),'complete_financial_upload_required')
        require(0<sum(len(v) for v in files.values())<=MAX_FINANCIAL_UPLOAD,'financial_upload_size_limit')
        require(type(expected_generation) is str and re.fullmatch(r'[0-9a-f]{64}',expected_generation),'invalid_base_generation')
        return self._enqueue((files,declared,expected_generation))
