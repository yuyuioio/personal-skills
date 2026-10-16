#!/usr/bin/env python3
"""Plan native EndNote attachments and verify exported library snapshots.

This helper never writes the EndNote database or registers attachments itself.
The agent performs Attach File through the available native desktop controller.
"""
from __future__ import annotations
import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from paper_bundle import attachment_path, digest, load_xml, match_records, normalize_doi, normalize_title, write_json


def checked_records(xml, library):
    records = load_xml(xml)
    if not records or any(not r['record_number'] for r in records):
        raise ValueError('Export must contain identified references')
    ids = [r['record_number'] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate record numbers in export')
    if any(not r.get('library_path') or os.path.normcase(str(Path(r['library_path']).resolve())) != os.path.normcase(str(library)) for r in records):
        raise ValueError('XML database paths do not match the active library')
    return records


def read_manifest(path):
    path = Path(path).resolve(strict=True)
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    source = manifest['source_pdf']
    if digest(source['path']) != source['sha256']:
        raise ValueError('Source PDF changed')
    summary = Path(manifest['outputs']['summary_markdown']).resolve(strict=True)
    if manifest.get('summary_status') != 'ready' or digest(summary) != manifest['outputs']['summary_sha256']:
        raise ValueError('Summary is missing or changed; package it again')
    return path, manifest, summary


def matching_attachments(record, library, summary_hash):
    result = []
    for uri in record['attachments']:
        path = attachment_path(uri, library)
        if path and path.is_file() and path.suffix.lower() == '.md' and digest(path) == summary_hash:
            result.append({'uri': uri, 'path': str(path), 'sha256': summary_hash})
    return result


def native_attachments(args, record, library):
    """Validate agent-observed native attachment inventory; never infer registration from disk."""
    evidence = getattr(args, 'native_observation', None)
    if not evidence:
        return [], None
    observation = json.loads(evidence.read_text(encoding='utf-8-sig'))
    if (Path(observation['library_path']).resolve(strict=True) != library
        or observation['record_number'] != record['record_number']
        or normalize_title(observation['title']) != normalize_title(record['title'])
        or normalize_doi(observation.get('doi', '')) != record['doi']
        or not observation.get('reference_reopened') or not observation.get('observed_at')):
        raise ValueError('Native observation does not establish the same reopened reference')
    result = []
    base = library.with_suffix('.Data') / 'PDF'
    for entry in observation['attachments']:
        actual = Path(entry['path']).resolve(strict=True)
        if not actual.is_relative_to(base.resolve()) or actual.name != entry['displayed_filename']:
            raise ValueError('Native observed attachment is not the displayed copied file')
        result.append('internal-pdf://' + actual.relative_to(base.resolve()).as_posix())
    if len(set(result)) != len(result):
        raise ValueError('Duplicate native attachments')
    return result, observation


def plan(args):
    path, manifest, summary = read_manifest(args.manifest)
    library = args.library.resolve(strict=True)
    if library.suffix.lower() != '.enl':
        raise ValueError('Use the active .enl library')
    records = checked_records(args.xml, library)
    match = match_records(manifest, records, str(library))
    if match['status'] != 'matched':
        raise ValueError(f"No unique strong match: {match['status']}; no attachment authorized")
    record = next(r for r in records if r['record_number'] == match['record_number'])
    native, observation = native_attachments(args, record, library)
    record = {**record, 'attachments': list(dict.fromkeys(record['attachments'] + native))}
    attached = matching_attachments(record, library, digest(summary))
    if len(attached) > 1:
        raise ValueError('Multiple identical summary attachments; review existing duplicates')
    # Preserve immutable summary bytes; authoritative live status is in the sidecar.
    previous_state = manifest.get('endnote', {})
    history = list(previous_state.get('writeback_history', []))
    if previous_state.get('verification') and previous_state['verification'] not in history:
        history.append(previous_state['verification'])
    manifest['endnote'] = {**match, 'database_id': record['database_id'], 'writeback_history': history,
        'xml_path': str(args.xml.resolve()), 'xml_sha256': digest(args.xml),
        'writeback_status': 'already_attached' if attached else 'planned',
        'writeback_plan': {'before_xml': str(args.xml.resolve()), 'before_sha256': digest(args.xml),
            'reference_count': len(records), 'record_number': record['record_number'],
            'title': record['title'], 'doi': record['doi'], 'original_attachments': record['attachments'],
            'summary_path': str(summary), 'summary_sha256': digest(summary),
            'action': 'skip_existing' if attached else 'attach_file', 'existing': attached,
            'native_observation': observation}}
    write_json(path, manifest)
    print(json.dumps(manifest['endnote']['writeback_plan'], ensure_ascii=False, indent=2))


def verify(args):
    path, manifest, summary = read_manifest(args.manifest)
    state = manifest['endnote']
    plan_data = state['writeback_plan']
    if digest(plan_data['before_xml']) != plan_data['before_sha256'] or digest(summary) != plan_data['summary_sha256']:
        raise ValueError('Plan inputs changed; replan before writeback')
    library = Path(state['library_path']).resolve(strict=True)
    before = checked_records(plan_data['before_xml'], library)
    after = checked_records(args.xml, library)
    before_by_id = {r['record_number']: r for r in before}
    after_by_id = {r['record_number']: r for r in after}
    if before_by_id.keys() != after_by_id.keys():
        raise ValueError('Reference set changed; check for created or removed references')
    number = plan_data['record_number']
    target = after_by_id[number]
    for record_id, previous in before_by_id.items():
        current = after_by_id[record_id]
        if {k:v for k,v in previous.items() if k != 'attachments'} != {k:v for k,v in current.items() if k != 'attachments'}:
            raise ValueError(f'Reference identity changed: {record_id}')
        if record_id != number and previous['attachments'] != current['attachments']:
            raise ValueError(f'Attachments changed on another reference: {record_id}')
    if Counter(before_by_id[number]['attachments']) - Counter(target['attachments']):
        raise ValueError('An original attachment was removed')
    native, observation = native_attachments(args, target, library)
    target = {**target, 'attachments': list(dict.fromkeys(target['attachments'] + native))}
    if Counter(plan_data['original_attachments']) - Counter(target['attachments']):
        raise ValueError('A planned original attachment is missing from native/export observations')
    matched = match_records(manifest, after, str(library))
    if matched['status'] != 'matched' or matched['record_number'] != number:
        raise ValueError('Reference no longer uniquely matches the source PDF/DOI')
    copies = matching_attachments(target, library, plan_data['summary_sha256'])
    if len(copies) != 1:
        raise ValueError('Expected one readable summary attachment with the exact file hash')
    additional = Counter(target['attachments']) - Counter(plan_data['original_attachments'])
    expected = Counter() if plan_data['action'] == 'skip_existing' else Counter([copies[0]['uri']])
    if additional != expected:
        raise ValueError('Unexpected or duplicate attachment additions')
    opened = getattr(args, 'opened_attachment', None)
    if opened and opened.resolve(strict=True) != Path(copies[0]['path']).resolve(strict=True):
        raise ValueError('Opened file is not the registered EndNote attachment')
    if opened and not getattr(args, 'opened_app', ''):
        raise ValueError('Record the observed application name for open verification')
    state['writeback_status'] = 'attached'
    state['verification'] = {'verified_at': datetime.now(timezone.utc).isoformat(),
        'after_xml': str(args.xml.resolve()), 'after_xml_sha256': digest(args.xml),
        'record_number': number, 'reference_count_before': len(before), 'reference_count_after': len(after),
        'original_attachments_preserved': True, 'attachment': copies[0],
        'content_readable': True, 'opened_in_app': bool(opened),
        'opened_app': getattr(args, 'opened_app', '') if opened else '',
        'native_observation_path': str(args.native_observation.resolve()) if observation else '',
        'native_observation_sha256': digest(args.native_observation) if observation else '',
        'action': plan_data['action'], 'evidence': 'Native reference attachment inventory plus XML identity/count/metadata and exact readable file copy' if observation else 'Exported attachment URI and exact readable file copy'}
    write_json(path, manifest)
    print(json.dumps(state['verification'], ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name, action in [('plan', plan), ('verify', verify)]:
        command = commands.add_parser(name)
        command.add_argument('--manifest', type=Path, required=True)
        command.add_argument('--xml', type=Path, required=True)
        command.add_argument('--native-observation', type=Path, help='Agent-observed native attachment inventory when XML omits non-PDFs')
        if name == 'plan':
            command.add_argument('--library', type=Path, required=True)
        else:
            command.add_argument('--opened-attachment', type=Path, help='Actual attachment path observed in native app UI')
            command.add_argument('--opened-app', help='Observed native app name; the agent must inspect it')
        command.set_defaults(action=action)
    args = parser.parse_args()
    try:
        args.action(args)
    except (OSError, ValueError, KeyError, ET.ParseError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
