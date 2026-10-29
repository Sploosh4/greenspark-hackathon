"""Check only explicit asset-manifest files; no network or mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

MANIFEST=Path(__file__).resolve().parents[2]/'docs/team-connect/ASSET-MANIFEST.json'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',required=True)
    parser.add_argument('--root',required=True,type=Path)
    args=parser.parse_args()
    data=json.loads(MANIFEST.read_text())
    if args.asset not in data['assets']:parser.error('Unknown asset group')
    requested=args.root.absolute()
    if requested.is_symlink() or any(p.is_symlink() for p in requested.parents):
        parser.error('Asset root must not use symlinks')
    root=requested.resolve(strict=True)
    errors=[];checked=0
    for name,expected in data['assets'][args.asset]['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise ValueError('Unsafe manifest path')
        path=root/relative
        if any(p.is_symlink() for p in [path,*path.parents] if p!=root.parent):
            errors.append({'file':name,'error':'symlink'});continue
        if not path.is_file() or not path.resolve().is_relative_to(root):
            errors.append({'file':name,'error':'missing regular file'});continue
        h=hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
        checked+=1
        if h.hexdigest()!=expected:errors.append({'file':name,'error':'SHA256 mismatch'})
    print(json.dumps({'asset':args.asset,'checked':checked,'expected':len(data['assets'][args.asset]['files']),'errors':errors,'contents_printed':False,'activated':False},indent=2))
    return 1 if errors else 0

if __name__=='__main__':sys.exit(main())
