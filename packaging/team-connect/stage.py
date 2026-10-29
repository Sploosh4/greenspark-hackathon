"""Create small, secret-free build contexts from read-only application snapshots."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

HERE = Path(__file__).resolve().parent
Q1 = HERE.parents[1] / 'apps/q1-customer-review'
Q3 = HERE.parents[1] / 'apps/q3-community-planning'
FONT = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
FONT_HASH = 'b4c632e3cdf9acc7f28758fb5a323c8524d7fc6660d46904d9b6cbe2809c419c'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def copy_file(source, target, manifest):
    if source.is_symlink() or not source.is_file():
        raise ValueError(f'Expected regular source file: {source}')
    # Reject symlinked ancestor paths too.
    if any(p.is_symlink() for p in source.parents):
        raise ValueError(f'Symlinked source parent: {source}')
    raw = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    manifest[str(source)] = sha(raw)


def paths(root, folder, suffixes):
    return [p.relative_to(root) for p in sorted((root / folder).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix in suffixes]


def selected_q1_files(q1):
    selected = [Path(p) for p in ('serve.py', 'pdf_export.py', 'index.html', 'app.mjs', 'core.mjs',
                                  'LICENSE', 'assets/q1.css', 'docs/UPLOAD-VALIDATION-CONTRACT.json')]
    if (q1/'checks.html').is_file():selected.append(Path('checks.html'))
    for tool in ['tools/build_replay_snapshot.py', 'tools/current_inference.py']:
        if (q1/tool).is_file():selected.append(Path(tool))
    selected += [p for p in paths(q1, 'assets', {'.html', '.mjs', '.css', '.svg'}) if p not in selected]
    return selected + paths(q1, 'prototype', {'.py'}) + paths(q1, 'prototype/vendor', {'.json', '.md'})


def stage_q1(q1, output):
    """Stage only Q1 into a fresh context; do not replace a reviewed snapshot."""
    q1, output = Path(q1), Path(output)
    if output.exists():
        raise ValueError(f'Refusing to overwrite snapshot: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.q1-stage-', dir=output.parent))
    manifest = {}
    try:
        for relative in selected_q1_files(q1):
            copy_file(q1 / relative, temp / 'app' / relative, manifest)
        for name in ['support.py', 'healthcheck.py', 'q1_launcher.py', 'private_identity.py']:
            copy_file(HERE / 'runtime' / name, temp / 'runtime' / name, manifest)
        copy_file(HERE / 'Dockerfile.q1', temp / 'Dockerfile', manifest)
        copy_file(HERE / '.dockerignore', temp / '.dockerignore', manifest)
        copy_file(HERE / 'requirements-q1.txt', temp / 'requirements-q1.txt', manifest)
        if sha(FONT.read_bytes()) != FONT_HASH:
            raise ValueError('Font differs from reviewed pin')
        copy_file(FONT, temp / 'font/DejaVuSans.ttf', manifest)
        copy_file(Path('/usr/share/doc/fonts-dejavu-core/copyright'), temp / 'font/LICENSE', manifest)
        if any(sha(Path(p).read_bytes()) != digest for p, digest in manifest.items()):
            raise ValueError('Source changed while staging; no context promoted')
        (temp / 'snapshot-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        os.rename(temp, output)
        return manifest
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def stage_q3_receipt(receipt_path, output):
    """Package a held, hash-pinned owner snapshot; never copy its runtime state."""
    receipt = json.loads(Path(receipt_path).read_text())
    source, output = Path(receipt.get('frozenSnapshot') or receipt['frozenSource']), Path(output)
    if (not source.resolve().is_relative_to(Path(receipt_path).resolve().parent)
            or source.name != 'season-ahead-frozen-' + receipt['codeVersionSha256'][:12]):
        raise ValueError('Frozen source must be the named sibling snapshot of its receipt')
    if output.exists():
        raise ValueError('Refusing to overwrite reviewed Q3 snapshot')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.q3-stage-', dir=output.parent))
    manifest = {}
    try:
        selected = []
        for relative, expected in receipt['runtimeFilesSha256'].items():
            p = Path(relative)
            if p.is_absolute() or not p.parts or '..' in p.parts or '\\' in relative:
                raise ValueError('Unsafe owner manifest path')
            allowed = (relative in {'run.py', 'BUSINESS-UPLOAD-CONTRACT.json', 'data/PROVENANCE.md'}
                       or p.parts[0] == 'server' and p.suffix == '.py'
                       or p.parts[0] == 'web' and p.suffix in {'.html', '.mjs', '.css', '.js', '.txt', '.svg', '.geojson'}
                       or p.parts[:2] in {('data', 'inputs'), ('data', 'geography'), ('data', 'financial')} and p.suffix == '.json'
                       or p.parts[:2] == ('data', 'history') and p.suffix in {'.png', '.json', '.gz'})
            if not allowed:
                continue
            path = source / p
            if path.is_symlink() or sha(path.read_bytes()) != expected:
                raise ValueError('Owner frozen source differs: ' + relative)
            selected.append(p)
        for relative in selected:
            copy_file(source / relative, temp / 'app' / relative, manifest)
        for name in ['support.py', 'healthcheck.py', 'q3_launcher.py', 'private_identity.py']:
            copy_file(HERE / 'runtime' / name, temp / 'runtime' / name, manifest)
        copy_file(HERE / 'Dockerfile.q3', temp / 'Dockerfile', manifest)
        copy_file(HERE / '.dockerignore', temp / '.dockerignore', manifest)
        if any(sha(Path(path).read_bytes()) != digest for path, digest in manifest.items()):
            raise ValueError('Frozen source changed while staging')
        (temp / 'snapshot-manifest.json').write_text(json.dumps({'owner_version': receipt['codeVersionSha256'],
                                                                'owner_receipt_sha256': sha(Path(receipt_path).read_bytes()),
                                                                'source_sha256': manifest, 'runtime_state_copied': False}, indent=2) + '\n')
        os.rename(temp, output)
        return manifest
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def stage(q1=Q1, q3=Q3, output=HERE / 'build'):
    q1, q3, output = Path(q1), Path(q3), Path(output)
    if output.exists():
        raise ValueError(f'Refusing to overwrite snapshot: {output}. Choose a new --output directory.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.stage-', dir=output.parent))
    manifest = {}
    try:
        q1_files = selected_q1_files(q1)
        q3_files = [Path('run.py'), Path('BUSINESS-UPLOAD-CONTRACT.json'), Path('data/PROVENANCE.md')] + paths(q3, 'server', {'.py'})
        q3_files += paths(q3, 'web', {'.html', '.mjs', '.css', '.js', '.txt', '.svg', '.geojson'})
        q3_files += paths(q3, 'data/inputs', {'.json'}) + paths(q3, 'data/geography', {'.json'}) + paths(q3, 'data/financial', {'.json'})
        for name, root, selected in [('q1', q1, q1_files), ('q3', q3, q3_files)]:
            context = temp / name
            for relative in selected:
                copy_file(root / relative, context / 'app' / relative, manifest)
            for file in ('support.py', 'healthcheck.py', f'{name}_launcher.py', 'private_identity.py'):
                copy_file(HERE / 'runtime' / file, context / 'runtime' / file, manifest)
            copy_file(HERE / f'Dockerfile.{name}', context / 'Dockerfile', manifest)
            copy_file(HERE / '.dockerignore', context / '.dockerignore', manifest)
        copy_file(HERE / 'requirements-q1.txt', temp / 'q1/requirements-q1.txt', manifest)
        if sha(FONT.read_bytes()) != FONT_HASH:
            raise ValueError('The reviewed DejaVu font differs; review and update its pin before staging.')
        copy_file(FONT, temp / 'q1/font/DejaVuSans.ttf', manifest)
        copy_file(Path('/usr/share/doc/fonts-dejavu-core/copyright'), temp / 'q1/font/LICENSE', manifest)
        # Detect concurrent edits while taking the snapshot. Restage once workers finish.
        if any(sha(Path(p).read_bytes()) != digest for p, digest in manifest.items()):
            raise ValueError('Source changed while staging. Retry after the application worker finishes.')
        (temp / 'snapshot-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        os.rename(temp, output)
        return manifest
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--q1', type=Path, default=Q1)
    parser.add_argument('--q3', type=Path, default=Q3)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--only', choices=['both', 'q1', 'q3-receipt'], default='both')
    parser.add_argument('--receipt', type=Path, help='Optional owner receipt for --only q3-receipt')
    args = parser.parse_args()
    output = args.output or HERE / {'both': 'build', 'q1': 'build/q1-verified', 'q3-receipt': 'build/q3-verified'}[args.only]
    result = stage(args.q1, args.q3, output) if args.only == 'both' else stage_q1(args.q1, output) if args.only == 'q1' else stage_q3_receipt(args.receipt, output)
    print(json.dumps({'output': str(output), 'source_files': len(result), 'scope': args.only}))
