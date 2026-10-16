#!/usr/bin/env python3
"""Render source-PDF crops and check their links in an EndNote Markdown bundle.

This validates files/provenance only. The reader must establish figure coverage,
choose bounding boxes, inspect crops, and verify every scientific explanation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else _digest(stream)


def _digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(block)
    return value.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def inside(root, relative):
    path = Path(relative)
    if not relative or path.is_absolute() or re.match(r'^[A-Za-z]:', str(relative)) or '\\' in str(relative):
        raise ValueError(f'Expected a package-relative forward-slash path: {relative}')
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes the paper package: {relative}')
    return target


def source_path(plan_path, entry):
    path = Path(entry['path'])
    return path.absolute() if path.is_absolute() else (plan_path.parent / path).absolute()


def validate_plan(plan):
    sources = plan.get('sources', {})
    items = plan.get('items', [])
    if 'main' not in sources or not items:
        raise ValueError('Inventory must define main source and nonempty items.')
    for label, source in sources.items():
        if not source.get('path') or not re.fullmatch(r'[a-fA-F0-9]{64}', source.get('sha256', '')):
            raise ValueError(f'Source {label} requires a PDF path and SHA-256.')
    ids = set()
    for item in items:
        name = item.get('id', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', name) or name in ids:
            raise ValueError(f'Invalid or duplicate item id: {name}')
        ids.add(name)
        if item.get('source') not in sources or item.get('kind') not in ('figure', 'table', 'scheme', 'image'):
            raise ValueError(f'Invalid source/kind for {name}')
        if not str(item.get('number', '')).strip():
            raise ValueError(f'Missing figure/table identifier for {name}')
        if type(item.get('page')) is not int or item['page'] < 1:
            raise ValueError(f'Physical page must be an integer starting at 1: {name}')
        if type(item.get('selected')) is not bool:
            raise ValueError(f'Explicit selected true/false required: {name}')
        if item['source'] == 'main' and not item['selected']:
            raise ValueError(f'Main-text figures/tables cannot be silently omitted: {name}')
        if item['source'] != 'main' and not item.get('selection_reason', '').strip():
            raise ValueError(f'SI selection/omission reason required: {name}')
        panels = item.get('panels', [])
        if not isinstance(panels, list) or not all(isinstance(p, str) and p for p in panels) or len(set(panels)) != len(panels):
            raise ValueError(f'Invalid or duplicate panels: {name}')
        if item['selected']:
            box = item.get('bbox')
            if not isinstance(box, list) or len(box) != 4 or not all(type(x) in (int, float) and math.isfinite(x) for x in box):
                raise ValueError(f'Expected normalized [left,top,right,bottom]: {name}')
            left, top, right, bottom = box
            if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
                raise ValueError(f'Crop outside page or empty: {name}')
    return plan


def render(plan_path, paper_dir, dpi=200, overwrite=False):
    import pypdfium2 as pdfium
    plan_path = Path(plan_path).absolute()
    paper_dir = Path(paper_dir).resolve()
    plan = validate_plan(read_json(plan_path))
    if not 72 <= dpi <= 600:
        raise ValueError('DPI must be between 72 and 600.')
    result_path = paper_dir / 'figure-assets.json'
    selected = [item for item in plan['items'] if item['selected']]
    targets = [inside(paper_dir, f"figures/{item['id']}.png") for item in selected]
    for target in targets + [result_path]:
        if target.exists() and not overwrite:
            raise ValueError(f'Output exists; use --overwrite for intentional regeneration: {target}')
    docs = {}
    try:
        sources, source_files = {}, {}
        for name, entry in plan['sources'].items():
            path = source_path(plan_path, entry)
            if sha256(path).lower() != entry['sha256'].lower():
                raise ValueError(f'Source changed or wrong PDF: {name}')
            doc = pdfium.PdfDocument(str(path))
            docs[name] = doc
            source_files[name] = path
            resolved = path.resolve()
            stored = resolved.relative_to(paper_dir).as_posix() if resolved.is_relative_to(paper_dir) else str(path)
            sources[name] = {**entry, 'path': stored, 'pages': len(doc)}
        for item in plan['items']:
            if item['page'] > len(docs[item['source']]):
                raise ValueError(f"Page outside PDF: {item['id']}")
        paper_dir.mkdir(parents=True, exist_ok=True)
        assets = []
        for item in plan['items']:
            asset = dict(item)
            if item['selected']:
                page = docs[item['source']][item['page'] - 1]
                bitmap = page.render(scale=dpi / 72)
                try:
                    image = bitmap.to_pil()
                    width, height = image.size
                    left, top, right, bottom = item['bbox']
                    pixels = (math.floor(left * width), math.floor(top * height),
                              math.ceil(right * width), math.ceil(bottom * height))
                    crop = image.crop(pixels)
                    target = inside(paper_dir, f"figures/{item['id']}.png")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    crop.save(target)
                    asset.update(asset=f"figures/{item['id']}.png", sha256=sha256(target),
                                 pixels=list(crop.size), page_pixels=[width, height], bbox_pixels=list(pixels),
                                 visual_review='pending', interpretation_review='pending')
                finally:
                    bitmap.close()
                    page.close()
            assets.append(asset)
        # Do not certify crops against a PDF that changed while rendering.
        for name, entry in sources.items():
            if sha256(source_files[name]).lower() != entry['sha256'].lower():
                raise ValueError(f'Source changed during rendering: {name}')
        result = {'schema_version': '1.0', 'dpi': dpi, 'sources': sources, 'items': assets,
                  'scope': 'File/provenance checks only; original-page inventory and scientific interpretation require reader review.'}
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return result_path
    finally:
        for doc in docs.values():
            doc.close()


def check(manifest_path, markdown_path):
    from PIL import Image
    manifest_path, markdown_path = Path(manifest_path).absolute(), Path(markdown_path).absolute()
    root = manifest_path.parent.resolve()
    if not markdown_path.resolve().is_relative_to(root):
        raise ValueError('Final Markdown must be inside the paper package.')
    data = validate_plan(read_json(manifest_path))
    errors, used = [], set()
    text = markdown_path.read_text(encoding='utf-8-sig')
    links = re.findall(r'!\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+["\'][^\n]*["\'])?\s*\)', text)
    for raw in links:
        link = unquote(raw.strip('<>'))
        if urlsplit(link).scheme or link.startswith('//'):
            errors.append(f'Expected a local package image, got: {link}')
            continue
        try:
            target = inside(root, (markdown_path.parent / link).relative_to(root).as_posix())
            with Image.open(target) as image:
                image.verify()
            used.add(target)
        except (OSError, ValueError) as error:
            errors.append(f'Invalid image link {link}: {error}')
    selected = [item for item in data['items'] if item['selected']]
    for item in selected:
        try:
            target = inside(root, item.get('asset', ''))
            if target not in used:
                errors.append(f"Selected figure/table not embedded: {item['id']}")
            if sha256(target) != item.get('sha256'):
                errors.append(f"Crop missing or changed: {item['id']}")
        except (ValueError, OSError) as error:
            errors.append(str(error))
    for name, entry in data['sources'].items():
        try:
            if sha256(source_path(manifest_path, entry)).lower() != entry['sha256'].lower():
                errors.append(f'Source changed since crop: {name}')
        except OSError as error:
            errors.append(f'Source unavailable for recheck: {name}: {error}')
    return {'structure_ok': not errors, 'selected': len(selected), 'images_linked': len(used),
            'omitted_si': [{'id': item['id'], 'reason': item['selection_reason']}
                           for item in data['items'] if not item['selected']],
            'reader_reviews_pending': [item['id'] for item in selected
                if item.get('visual_review') != 'checked' or item.get('interpretation_review') != 'checked'],
            'errors': errors,
            'limit': 'Does not prove complete original-figure coverage, legible crops, correct captions/labels, or scientific conclusions.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    crop = commands.add_parser('render', help='Render verified PDF crops from a reader-authored inventory.')
    crop.add_argument('--plan', type=Path, required=True)
    crop.add_argument('--paper-dir', type=Path, required=True)
    crop.add_argument('--dpi', type=int, default=200)
    crop.add_argument('--overwrite', action='store_true')
    audit = commands.add_parser('check', help='Check file integrity and final Markdown image links, not scientific meaning.')
    audit.add_argument('--manifest', type=Path, required=True)
    audit.add_argument('--markdown', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'render':
            print(json.dumps({'manifest': str(render(args.plan, args.paper_dir, args.dpi, args.overwrite))}, ensure_ascii=False))
        else:
            result = check(args.manifest, args.markdown)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not result['structure_ok']:
                return 2
    except (OSError, ValueError, ImportError, KeyError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
