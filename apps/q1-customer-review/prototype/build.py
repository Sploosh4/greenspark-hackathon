"""Reproduce the retained calculated review without changing any source file."""
import argparse
import hashlib
import json
from pathlib import Path
from .review import build_review,REVIEW_DATE
from .inputs import DEFAULT_SOURCE

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--review-date',default=REVIEW_DATE)
    parser.add_argument('--out',type=Path,default=Path(__file__).parent/'reports/current-review.json')
    args=parser.parse_args()
    if args.out.resolve().is_relative_to(args.source.resolve()):
        parser.error('Derived output cannot overwrite the immutable source package')
    review=build_review(args.source,review_date=args.review_date)
    encoded=json.dumps(review,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(encoded+b'\n')
    print(json.dumps({'output':str(args.out),'sha256':hashlib.sha256(encoded).hexdigest(),'review_date':review['review_date'],'customers':len(review['customers']),'events':len(review['events']),'method':review['method']['id']}))
