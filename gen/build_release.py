"""Build a distributable PopTracker pack zip.

Layout is manifest-at-root, which PopTracker accepts (a single wrapping folder
also works). Dev-only files are excluded, including .luarc.json - PACKS.md
recommends checking that into git but leaving it out of the final pack.

Usage:  python gen/build_release.py [output_dir]
"""
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)

SKIP_DIRS = {'.git', 'gen', '__pycache__', 'dist'}
SKIP_FILES = {'.gitignore', '.luarc.json'}
SKIP_SUFFIX = ('.bak', '.pyc')


def collect():
    out = []
    for dirpath, dirnames, filenames in os.walk(PACK):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in sorted(filenames):
            if f in SKIP_FILES or f.endswith(SKIP_SUFFIX):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, PACK).replace(os.sep, '/')
            out.append((full, rel))
    return out


def referenced_images(names):
    """Every image path mentioned in the pack's json, for a completeness check."""
    blob = []
    for full, rel in names:
        if rel.endswith('.json'):
            with open(full, encoding='utf-8') as fh:
                blob.append(fh.read())
    refs = set()
    for m in re.findall(r'"([^"]*images/[^"]+\.png)"', '\n'.join(blob)):
        refs.add(m.lstrip('/'))
    return refs


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PACK, 'dist')
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(PACK, 'manifest.json'), encoding='utf-8') as fh:
        manifest = json.load(fh)
    version = manifest['package_version']
    path = os.path.join(out_dir, 'acnh_ap_tracker-v%s.zip' % version)

    files = collect()
    present = {rel for _, rel in files}

    missing = sorted(r for r in referenced_images(files) if r not in present)
    if missing:
        print('WARNING: %d referenced images are not in the pack:' % len(missing))
        for m in missing[:10]:
            print('   ' + m)

    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for full, rel in files:
            z.write(full, rel)

    size = os.path.getsize(path) / 1e6
    print('wrote %s' % path)
    print('%d files, %.1f MB, version %s' % (len(files), size, version))
    names = zipfile.ZipFile(path).namelist()
    print('manifest at zip root: %s' % ('manifest.json' in names))
    print('top-level dirs: %s' % sorted({n.split('/')[0] for n in names if '/' in n}))
    print('root files: %s' % sorted(n for n in names if '/' not in n))
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main())
