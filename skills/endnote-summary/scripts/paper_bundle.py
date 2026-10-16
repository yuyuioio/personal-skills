#!/usr/bin/env python3
"""Prepare evidence-linked PDF summaries and read-only EndNote match manifests."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

DOI_PATTERN = re.compile(r'10\.\d{4,9}/[^\s"<>]+', re.IGNORECASE)


def utf16_length(value):
    return len(value.encode('utf-16-le')) // 2


def clip_utf16(value, limit):
    result = ''
    for character in value:
        if utf16_length(result + character) > limit:
            break
        result += character
    return result.rstrip(' .')


def filename_component(value):
    """Preserve readable Unicode while rejecting Windows path syntax."""
    value = unicodedata.normalize('NFC', str(value))
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', value)
    value = re.sub(r'\s+', ' ', value).strip(' .')
    device = value.split('.')[0].upper()
    if device in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} or re.fullmatch(r'(COM|LPT)[1-9¹²³]', device):
        value = '_' + value
    return value or '未命名文献'


def paper_label(bibliography, fallback_title):
    title = filename_component(bibliography.get('title') or fallback_title)
    doi = bibliography.get('doi', '')
    status = bibliography.get('doi_status', 'missing')
    if doi and status == 'verified':
        label = filename_component(doi)
    elif doi:
        label = filename_component(doi) + '__DOI待核验'
    else:
        label = 'DOI待核验' if status == 'unresolved' else '无DOI'
    return title, label


def create_paper_folder(root, bibliography, fallback_title):
    """Create a fresh title/DOI folder; never reuse an earlier delivery."""
    title, label = paper_label(bibliography, fallback_title)
    # Leave room for hash-based evidence files and a repeated-delivery suffix.
    available = min(220, 240 - utf16_length(str(root.resolve())) - 1 - 40)
    if available < 48:
        raise ValueError('Storage root is too long; choose a shorter output directory')
    label_limit = available - 2 - 12 - 8
    if utf16_length(label) > label_limit:
        label = clip_utf16(label, label_limit - 10) + '__' + hashlib.sha256(label.encode()).hexdigest()[:8]
    # Prefer the complete title/DOI in the Markdown filename; shorten its parent first.
    minimum_folder = utf16_length(label) + 2 + 12 + 8
    summary_reserve = max(40, utf16_length(title + '__' + label + '.md') + 18)
    summary_reserve = min(summary_reserve, 240 - utf16_length(str(root.resolve())) - 2 - minimum_folder)
    available = min(available, 240 - utf16_length(str(root.resolve())) - 2 - summary_reserve)
    title_limit = available - 2 - utf16_length(label) - 8
    base = clip_utf16(title, title_limit) + '__' + label
    root.mkdir(parents=True, exist_ok=True)
    for number in range(1, 10000):
        candidate = root / (base if number == 1 else f'{base}__{number}')
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise ValueError('Too many existing deliveries with this name; choose another storage root')


def summary_path(manifest, folder):
    """Choose a readable filename and protect unrelated existing files."""
    title, label = paper_label(manifest['bibliography'], Path(manifest['source_pdf']['filename']).stem)
    # Use title/DOI for every layout, retaining the legacy Windows path safeguards.
    available = min(220, 240 - utf16_length(str(folder.resolve())) - 1)
    if available < 48:
        raise ValueError('Output path is too long; choose a shorter output directory')
    # Reserve space for a collision suffix as well as extension/separator/title.
    label_limit = available - 4 - 2 - 18 - 12
    if utf16_length(label) > label_limit:
        label = clip_utf16(label, label_limit - 10) + '__' + hashlib.sha256(label.encode()).hexdigest()[:8]
    title_limit = available - 4 - 2 - utf16_length(label) - 18
    base = clip_utf16(title, title_limit) + '__' + label
    candidate = folder / (base + '.md')

    def owned(path):
        if not path.exists():
            return True
        if not path.is_file() or path.is_symlink():
            return False
        with path.open(encoding='utf-8-sig') as stream:
            if stream.readline().strip() != '---':
                return False
            for _ in range(80):
                line = stream.readline()
                if not line or line.strip() == '---':
                    break
                if line.startswith('paper_id:'):
                    try:
                        return json.loads(line.split(':', 1)[1]) == manifest['paper_id']
                    except (ValueError, TypeError):
                        return False
        return False

    if owned(candidate):
        return candidate
    fingerprint = manifest['source_pdf']['sha256']
    for count in range(8, 17, 4):
        candidate = folder / (base + '__' + fingerprint[:count] + '.md')
        if owned(candidate):
            return candidate
    raise ValueError('Filename collision cannot be resolved; choose a different output directory')


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def normalize_doi(value):
    value = unquote(str(value or '')).strip()
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)', '', value, flags=re.I)
    value = value.rstrip('.,;:')
    for left, right in [('(', ')'), ('[', ']'), ('{', '}')]:
        while value.endswith(right) and value.count(right) > value.count(left):
            value = value[:-1]
    if not DOI_PATTERN.fullmatch(value):
        return ''
    return value.casefold()


def normalize_title(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def collect_dois(pages, metadata):
    evidence = []
    sources = [('pdf_metadata', None, json.dumps(metadata, ensure_ascii=False, default=str))]
    sources += [('page_text', i + 1, text) for i, text in enumerate(pages[:2])]
    for source, page, text in sources:
        for found in DOI_PATTERN.finditer(text):
            doi = normalize_doi(found.group())
            if doi:
                item = {'doi': doi, 'source': source, 'page': page,
                        'context': text[max(0, found.start()-100):found.end()+100]}
                if item not in evidence:
                    evidence.append(item)
    return evidence


def load_xml(path):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('EndNote XML exceeds 64 MiB')
    payload = path.read_bytes()
    # Check UTF-8/16/32 spellings before parsing entity-bearing XML.
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', payload.replace(b'\x00', b''), re.I):
        raise ValueError('DTD and entities are not supported')
    root = ET.fromstring(payload)
    for node in root.iter():
        node.tag = node.tag.split('}')[-1]

    def text(node, query):
        item = node.find(query)
        return ''.join(item.itertext()).strip() if item is not None else ''

    records = []
    for node in root.findall('.//record'):
        metadata_node = copy.deepcopy(node)
        for parent in metadata_node.iter():
            for child in list(parent):
                if child.tag == 'pdf-urls':
                    parent.remove(child)
        records.append({
            'record_number': text(node, 'rec-number'),
            'library_path': node.find('database').get('path', '') if node.find('database') is not None else '',
            'database_id': text(node, 'foreign-keys/key') and (node.find('foreign-keys/key').get('db-id', '') or ''),
            'metadata_sha256': hashlib.sha256(ET.tostring(metadata_node, encoding='utf-8')).hexdigest(),
            'title': text(node, 'titles/title'),
            'year': text(node, 'dates/year'),
            'authors': [''.join(a.itertext()).strip() for a in node.findall('contributors/authors/author')],
            'doi': normalize_doi(text(node, 'electronic-resource-num')),
            'attachments': [''.join(a.itertext()).strip() for a in node.findall('urls/pdf-urls/url')],
        })
    return records


def attachment_path(value, library):
    if value.startswith('internal-pdf://'):
        if not library:
            return None
        base = Path(library).with_suffix('.Data') / 'PDF'
        relative = unquote(value[len('internal-pdf://'):]).replace('\\', '/')
        target = (base / relative).resolve()
        if not target.is_relative_to(base.resolve()):
            return None
        return target
    if value.lower().startswith('file:'):
        uri = urlparse(value)
        if uri.netloc and uri.netloc.lower() != 'localhost':
            return None  # Do not access network shares from XML instructions.
        local = unquote(uri.path)
        if re.match(r'^/[A-Za-z]:/', local):
            local = local[1:]
        return Path(local)
    path = Path(value)
    return path if path.is_absolute() else None


def match_records(manifest, records, library):
    candidates = []
    bibliography = manifest['bibliography']
    selected_doi = bibliography.get('doi', '')
    trusted_doi = selected_doi if bibliography.get('doi_status') == 'verified' else ''
    for record in records:
        reasons = []
        for value in record['attachments']:
            path = attachment_path(value, library)
            if path and path.suffix.lower() == '.pdf' and path.is_file():
                try:
                    if digest(path) == manifest['source_pdf']['sha256']:
                        reasons.append('pdf_sha256')
                        break
                except OSError:
                    continue
        if trusted_doi and trusted_doi == record['doi']:
            reasons.append('verified_doi')
        title = bibliography.get('title', '')
        if title and normalize_title(title) == normalize_title(record['title']):
            reasons.append('normalized_title')
        if reasons:
            candidates.append({**record, 'reasons': reasons})
    strongest = [c for c in candidates if 'pdf_sha256' in c['reasons'] or 'verified_doi' in c['reasons']]
    conflicts = [c for c in strongest if trusted_doi and c['doi'] and c['doi'] != trusted_doi]
    if conflicts or len(strongest) > 1:
        status, selected = 'ambiguous', None
    elif len(strongest) == 1 and library and strongest[0]['record_number']:
        status, selected = 'matched', strongest[0]['record_number']
    else:
        status, selected = ('review_required' if candidates else 'not_found'), None
    return {'status': status, 'library_path': library, 'record_number': selected,
            'candidates': candidates, 'writeback_status': 'not_attempted'}


def read_bibliography(path):
    fields = {'doi': '', 'doi_status': 'missing', 'doi_evidence': [],
              'title': '', 'authors': [], 'year': '', 'journal': '', 'sources': []}
    if path:
        supplied = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        for key in fields:
            if key in supplied:
                fields[key] = supplied[key]
        for key in ('doi', 'doi_status', 'title', 'year', 'journal'):
            if not isinstance(fields[key], str):
                raise ValueError(f'bibliography.{key} must be a string')
        for key in ('authors', 'sources', 'doi_evidence'):
            if not isinstance(fields[key], list):
                raise ValueError(f'bibliography.{key} must be a list')
        if fields['doi']:
            normalized = normalize_doi(fields['doi'])
            if not normalized:
                raise ValueError('Invalid DOI syntax; do not invent one')
            fields['doi'] = normalized
        if fields['doi_status'] not in ('missing', 'candidate', 'verified', 'unresolved'):
            raise ValueError('Unsupported DOI status')
        if fields['doi_status'] == 'verified' and (not fields['doi'] or not fields['doi_evidence']):
            raise ValueError('Verified DOI requires a DOI and evidence')
        if not fields['doi']:
            fields['doi_status'] = 'missing'
    return fields


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare(args):
    from pypdf import PdfReader
    source = args.pdf.resolve(strict=True)
    if source.suffix.lower() != '.pdf' or not source.is_file():
        raise ValueError('Input must be a local PDF file')
    fingerprint = digest(source)
    reader = PdfReader(source)
    if reader.is_encrypted and not reader.decrypt(''):
        raise ValueError('Encrypted PDF needs an authorized decrypted copy')
    pages = [page.extract_text() or '' for page in reader.pages]
    if digest(source) != fingerprint:
        raise ValueError('Source PDF changed during extraction')
    bibliography = read_bibliography(args.bibliography)
    candidates = collect_dois(pages, dict(reader.metadata or {}))
    if not bibliography['doi'] and candidates:
        bibliography['doi_status'] = 'unresolved'
    library = str(args.library.resolve(strict=True)) if args.library else ''
    if library and Path(library).suffix.lower() != '.enl':
        raise ValueError('--library must be the active .enl, not a compressed .enlx')
    stem = f'paper-{fingerprint[:16]}'
    output = args.output_dir.resolve()
    storage_root = output
    if getattr(args, 'paper_folder', False):
        output = create_paper_folder(storage_root, bibliography, source.stem)
    output.mkdir(parents=True, exist_ok=True)
    source_md, match_json = output / f'{stem}.source.md', output / f'{stem}.match.json'
    if not args.overwrite and (source_md.exists() or match_json.exists()):
        raise ValueError('Outputs already exist; use --overwrite for intentional regeneration')
    manifest = {
        'schema_version': '2.0', 'paper_id': f'sha256:{fingerprint}',
        'delivery_mode': 'manual_attachment',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_pdf': {'path': str(source), 'filename': source.name, 'sha256': fingerprint,
                       'pages': len(pages)},
        'extraction': {'method': 'pypdf_text', 'characters': sum(map(len, pages)),
                       'status': 'text_extracted' if any(p.strip() for p in pages) else 'ocr_required'},
        'bibliography': bibliography, 'doi_candidates': candidates,
        'endnote': {'status': 'not_checked', 'library_path': library,
                    'record_number': None, 'candidates': [], 'writeback_status': 'not_attempted'},
        'outputs': {'source_markdown': str(source_md), 'summary_markdown': '', 'research_notes': ''},
        'summary_status': 'pending',
    }
    if getattr(args, 'paper_folder', False):
        manifest['storage'] = {'layout': 'title_doi_folder', 'root': str(storage_root),
                               'paper_directory': str(output)}
    if args.endnote_xml:
        manifest['endnote'] = match_records(manifest, load_xml(args.endnote_xml), library)
        manifest['endnote']['xml_path'] = str(args.endnote_xml.resolve())
        manifest['endnote']['xml_sha256'] = digest(args.endnote_xml)
    source_text = '\n\n'.join(f'## PDF page {i+1}\n\n{text}' for i, text in enumerate(pages))
    source_md.write_text(source_text + '\n', encoding='utf-8')
    write_json(match_json, manifest)
    print(json.dumps({'manifest': str(match_json), 'source': str(source_md),
                      'doi_candidates': sorted({c['doi'] for c in candidates}),
                      'endnote_status': manifest['endnote']['status']}, ensure_ascii=False))


def package(args):
    manifest_path = args.manifest.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if digest(Path(manifest['source_pdf']['path'])) != manifest['source_pdf']['sha256']:
        raise ValueError('Source PDF fingerprint changed; prepare again')
    body = args.body.read_text(encoding='utf-8-sig').strip()
    if not body or body.startswith('---'):
        raise ValueError('Provide a nonempty summary body without frontmatter')
    if manifest['extraction']['status'] == 'ocr_required':
        raise ValueError('Empty extraction: complete OCR and update extraction evidence first')
    prefix = manifest_path.name.removesuffix('.match.json')
    summary = summary_path(manifest, manifest_path.parent)
    notes = manifest_path.parent / f'{prefix}.notes.txt'
    if not args.overwrite and (summary.exists() or (args.notes and notes.exists())):
        raise ValueError('Summary exists; use --overwrite for intentional regeneration')
    # Regeneration is a new local delivery, never evidence that these bytes were attached.
    if manifest['endnote'].get('writeback_status') != 'not_attempted' or manifest['endnote'].get('verification'):
        manifest.setdefault('previous_deliveries', []).append({
            'outputs': copy.deepcopy(manifest['outputs']),
            'endnote': copy.deepcopy(manifest['endnote'])})
    manifest['delivery_mode'] = 'manual_attachment'
    manifest['endnote']['writeback_status'] = 'not_attempted'
    manifest['endnote'].pop('verification', None)
    manifest['endnote'].pop('writeback_plan', None)
    fields = {'schema_version': manifest['schema_version'], 'paper_id': manifest['paper_id'],
              'doi': manifest['bibliography']['doi'], 'doi_status': manifest['bibliography']['doi_status'],
              'title': manifest['bibliography']['title'], 'authors': manifest['bibliography']['authors'],
              'year': manifest['bibliography']['year'], 'source_pdf': manifest['source_pdf']['path'],
              'source_sha256': manifest['source_pdf']['sha256'],
              'endnote_library': manifest['endnote']['library_path'],
              'endnote_record_number': manifest['endnote']['record_number'],
              'match_status': manifest['endnote']['status'],
              'writeback_status': manifest['endnote']['writeback_status'],
              'match_manifest': str(manifest_path), 'summary_status': 'ready',
              'delivery_mode': 'manual_attachment'}
    lines = ['---']
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f'{key}:' if value else f'{key}: []')
            lines.extend(f'  - {json.dumps(v, ensure_ascii=False)}' for v in value)
        else:
            lines.append(f'{key}: {json.dumps(value, ensure_ascii=False)}')
    lines += ['---', '', body, '']
    summary.write_text('\n'.join(lines), encoding='utf-8')
    manifest['outputs']['summary_markdown'] = str(summary)
    manifest['outputs']['summary_sha256'] = digest(summary)
    if args.notes:
        notes.write_text(args.notes.read_text(encoding='utf-8-sig'), encoding='utf-8')
        manifest['outputs']['research_notes'] = str(notes)
    manifest['summary_status'] = 'ready'
    manifest['summarized_at'] = datetime.now(timezone.utc).isoformat()
    write_json(manifest_path, manifest)
    print(json.dumps({'summary': str(summary), 'writeback_status': manifest['endnote']['writeback_status']}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    first = commands.add_parser('prepare', help='Extract PDF text and produce a match manifest')
    first.add_argument('--pdf', type=Path, required=True)
    first.add_argument('--output-dir', type=Path, required=True)
    first.add_argument('--bibliography', type=Path, help='Evidence-backed bibliography JSON')
    first.add_argument('--paper-folder', action='store_true',
                       help='Create a fresh title/DOI folder inside --output-dir for this delivery')
    first.add_argument('--endnote-xml', type=Path, help='Read-only exported EndNote XML')
    first.add_argument('--library', type=Path, help='Active .enl path for library-scoped matching')
    first.add_argument('--overwrite', action='store_true')
    first.set_defaults(action=prepare)
    second = commands.add_parser('package', help='Package an agent-written, evidence-linked summary')
    second.add_argument('--manifest', type=Path, required=True)
    second.add_argument('--body', type=Path, required=True)
    second.add_argument('--notes', type=Path)
    second.add_argument('--overwrite', action='store_true')
    second.set_defaults(action=package)
    args = parser.parse_args()
    try:
        args.action(args)
    except (ValueError, OSError, ET.ParseError, ImportError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
