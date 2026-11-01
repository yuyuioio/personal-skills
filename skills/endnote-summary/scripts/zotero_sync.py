#!/usr/bin/env python3
"""Prepare a verified Zotero attachment plan, then verify native Zotero writes.

Reads the local Desktop API only. The emitted JavaScript uses Zotero's own
Attachments API in Tools > Developer > Run JavaScript; no SQLite writes.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import mimetypes
import os
from pathlib import Path
import platform
import re
import sys
import unicodedata
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import build_opener, ProxyHandler


BASE = 'http://127.0.0.1:23119/api/users/0/'
HTTP = build_opener(ProxyHandler({}))
KNOWN_HOSTS = {'yuyuioio270k': 'current', 'yuyuioio': 'previous'}


def machine_name():
    return os.environ.get('COMPUTERNAME') or platform.node()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def normal_title(value):
    value = html.unescape(unicodedata.normalize('NFKC', value)).strip().strip('<>')
    value = re.sub(r'</?(?:i|b|em|strong|sub|sup)>', '', value, flags=re.I)
    value = re.sub(r'\.pdf\s*$', '', value, flags=re.I)
    return ''.join(c for c in value.casefold() if c.isalnum())


def normal_doi(value):
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.I).casefold()


def get(route):
    with HTTP.open(BASE + route, timeout=15) as response:
        return json.load(response)


def file_path(url):
    parsed = urlparse(url)
    if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost'):
        raise ValueError('Expected a local attachment file URL')
    value = unquote(parsed.path)
    if re.match(r'^/[A-Za-z]:/', value):
        value = value[1:]
    return Path(value)


def attachment_path(item):
    enclosure = item.get('links', {}).get('enclosure', {}).get('href')
    if enclosure:
        return file_path(enclosure)
    value = get('items/' + item['key'] + '/file/view/url')
    if isinstance(value, dict):
        value = value.get('url', '')
    return file_path(value)


def candidates(title, doi):
    found = {}
    for query in dict.fromkeys(filter(None, [doi, title])):
        start = 0
        while True:
            rows = get('items?' + urlencode({'q': query, 'limit': 100, 'start': start}))
            for row in rows:
                data = row['data']
                if data.get('itemType') not in ('note', 'attachment') and not data.get('deleted'):
                    found[row['key']] = row
            if len(rows) < 100:
                break
            start += 100
    matches = []
    for row in found.values():
        data = row['data']
        actual_doi = normal_doi(data.get('DOI', ''))
        title_ok = normal_title(data.get('title', '')) == normal_title(title)
        doi_ok = bool(doi and actual_doi and actual_doi == normal_doi(doi))
        if title_ok and doi and actual_doi and not doi_ok:
            raise ValueError('Same-title item has a conflicting DOI: ' + row['key'])
        if title_ok or doi_ok:
            matches.append(row)
    if len(matches) != 1:
        raise ValueError('Expected one existing parent item; found ' + str(len(matches))
                         + '. Do not create a replacement record or guess a duplicate.')
    return matches[0]


def make_html(source, title):
    try:
        import markdown
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent / '_vendor'))
        import markdown
    text = source.read_text(encoding='utf-8-sig')
    text = re.sub(r'\A---\s*\n.*?\n---\s*\n', '', text, count=1, flags=re.S)
    content = markdown.markdown(text, extensions=['tables', 'fenced_code', 'sane_lists'])
    image_hashes = []
    root = source.parent.resolve()

    def embed(match):
        raw = html.unescape(match.group(1))
        parsed = urlparse(raw)
        if parsed.scheme or raw.startswith('//'):
            raise ValueError('Summary images must be local package resources: ' + raw)
        path = (root / unquote(raw)).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Image escapes the article folder: ' + raw)
        mime = mimetypes.guess_type(path.name)[0]
        if mime not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
            raise ValueError('Expected a raster source crop: ' + raw)
        image_hashes.append({'path': path.relative_to(root).as_posix(), 'sha256': digest(path)})
        return 'src="data:' + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode() + '"'

    content = re.sub(r'src="([^"]+)"', embed, content)
    style = ('body{max-width:1100px;margin:40px auto;padding:0 24px;font:17px/1.8 '
             '"Microsoft YaHei",sans-serif;color:#20232a}img{max-width:100%;height:auto}'
             'table{border-collapse:collapse;display:block;overflow:auto}td,th{border:1px solid '
             '#ccd1d8;padding:8px}th{background:#f1f4f8}code{overflow-wrap:anywhere}'
             '@media print{body{margin:0;font-size:11pt}img{max-height:95vh;object-fit:contain}}')
    marker = '<!-- endnote-summary-source-sha256:' + digest(source) + ' -->'
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>'
            + html.escape(title) + '</title><style>' + style + '</style></head><body>'
            + marker + content + '</body></html>'), image_hashes


NATIVE = r'''// Run this reviewed file in Zotero's native Run JavaScript window.
// Pasting code containing await enables its async mode automatically.
const plan = __PLAN__;
const norm = value => value.normalize('NFKC').trim().replace(/^<|>$/g, '')
  .replace(/<\/?(?:i|b|em|strong|sub|sup)>/gi, '').replace(/\.pdf\s*$/i, '')
  .toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
const machine = Components.classes['@mozilla.org/process/environment;1']
  .getService(Components.interfaces.nsIEnvironment).get('COMPUTERNAME');
if (machine.toLowerCase() !== plan.machine_name.toLowerCase()) throw new Error('Computer changed; prepare again');
const parent = await Zotero.Items.getByLibraryAndKeyAsync(Zotero.Libraries.userLibraryID, plan.parent_key);
if (!parent || !parent.isRegularItem() || parent.deleted) throw new Error('Parent missing');
if (norm(parent.getField('title')) !== plan.parent_normal_title) throw new Error('Parent title changed');
const actualDoi = parent.getField('DOI').replace(/^https?:\/\/(dx\.)?doi\.org\//i, '').trim().toLowerCase();
if (actualDoi && plan.doi && actualDoi !== plan.doi.toLowerCase()) throw new Error('Parent DOI conflict');
const stored = await IOUtils.readUTF8(plan.html_path);
if (!stored.includes('endnote-summary-source-sha256:' + plan.markdown_sha256)) throw new Error('Source marker mismatch');
let saved = null;
for (const id of parent.getAttachments()) {
  const item = await Zotero.Items.getAsync(id);
  if (item.deleted || item.attachmentContentType !== 'text/html') continue;
  const path = await item.getFilePathAsync();
  if (path && await IOUtils.exists(path)) {
    const old = await IOUtils.readUTF8(path);
    if (old === stored) { saved = item; break; }
  }
}
const reused = !!saved;
if (!saved) saved = await Zotero.Attachments.importFromFile({
  file: plan.html_path, parentItemID: parent.id,
  title: plan.attachment_title, contentType: 'text/html', charset: 'utf-8'
});
const result = {status: reused ? 'already_present' : 'saved', machine_name: machine,
  parent_key: parent.key, attachment_key: saved.key, parent_id: parent.id,
  attachment_path: await saved.getFilePathAsync(), markdown_sha256: plan.markdown_sha256};
await Zotero.File.putContentsAsync(plan.native_result_path, JSON.stringify(result, null, 2));
await Zotero.getActiveZoteroPane().selectItem(parent.id);
return JSON.stringify(result, null, 2);
'''


def prepare(args):
    manifest_path = args.manifest.resolve(strict=True)
    manifest = read_json(manifest_path)
    if manifest.get('summary_status') != 'ready':
        raise ValueError('Finish and check the summary before synchronizing')
    source = Path(manifest['outputs']['summary_markdown']).resolve(strict=True)
    if source.parent != manifest_path.parent:
        raise ValueError('Summary must be inside this article package')
    if digest(source) != manifest['outputs']['summary_sha256']:
        raise ValueError('Summary changed after packaging; package again first')
    bib = manifest['bibliography']
    doi = bib['doi'] if bib.get('doi_status') == 'verified' else ''
    parent = candidates(bib['title'], doi)
    children = get('items/' + parent['key'] + '/children')
    evidence = []
    if normal_doi(parent['data'].get('DOI', '')) == normal_doi(doi) and doi:
        evidence.append('verified DOI')
    if normal_title(parent['data'].get('title', '')) == normal_title(bib['title']):
        evidence.append('normalized exact title')
    for item in children:
        if item['data'].get('contentType') == 'application/pdf':
            path = attachment_path(item)
            if path.is_file() and digest(path) == manifest['source_pdf']['sha256']:
                evidence.append('source PDF SHA-256; attachment ' + item['key'])
    output, images = make_html(source, bib['title'])
    html_path = source.with_suffix('.html')
    html_path.write_text(output, encoding='utf-8')
    root = source.parent
    plan = {'machine_name': machine_name(), 'machine_role': KNOWN_HOSTS.get(machine_name().casefold(), 'unrecognized_discover_current_paths'),
            'manifest': str(manifest_path), 'parent_key': parent['key'],
            'parent_title': parent['data']['title'], 'parent_normal_title': normal_title(parent['data']['title']),
            'doi': doi, 'match_evidence': evidence, 'markdown_path': str(source),
            'markdown_sha256': digest(source), 'html_path': str(html_path), 'html_sha256': digest(html_path),
            'images': images, 'attachment_title': '中文逐图总结 · ' + (doi or bib['title']),
            'native_result_path': str(root / 'zotero-native-result.json')}
    write_json(root / 'zotero-sync-plan.json', plan)
    (root / 'zotero-attach.js').write_text(NATIVE.replace('__PLAN__', json.dumps(plan, ensure_ascii=False)), encoding='utf-8')
    manifest['delivery_mode'] = 'zotero_attachment'
    manifest['zotero'] = {'machine_name': machine_name(), 'parent_key': parent['key'], 'match_evidence': evidence,
                          'writeback_status': 'prepared', 'cloud_sync_status': 'not_verified'}
    manifest['outputs']['zotero_html'] = str(html_path)
    write_json(manifest_path, manifest)
    return {'plan': str(root / 'zotero-sync-plan.json'), 'native_script': str(root / 'zotero-attach.js'),
            'parent_key': parent['key'], 'match_evidence': evidence, 'embedded_images': len(images),
            'machine_name': machine_name(), 'html_bytes': html_path.stat().st_size}


def verify(args):
    plan_path = args.plan.resolve(strict=True)
    plan = read_json(plan_path)
    if machine_name().casefold() != plan['machine_name'].casefold():
        raise ValueError('Computer changed; prepare a new plan')
    if digest(Path(plan['markdown_path'])) != plan['markdown_sha256'] or digest(Path(plan['html_path'])) != plan['html_sha256']:
        raise ValueError('Source files changed since preparation')
    children = get('items/' + plan['parent_key'] + '/children')
    matches = []
    for item in children:
        if item['data'].get('contentType') != 'text/html':
            continue
        path = attachment_path(item)
        if path.is_file() and digest(path) == plan['html_sha256']:
            matches.append((item, path))
    if len(matches) != 1:
        raise ValueError('Expected exactly one byte-identical saved attachment; found ' + str(len(matches)))
    item, path = matches[0]
    text = path.read_text(encoding='utf-8')
    images = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', text)
    image_hashes = [hashlib.sha256(base64.b64decode(value.split(',', 1)[1], validate=True)).hexdigest()
                    for value in images if value.startswith('data:image/')]
    if image_hashes != [row['sha256'] for row in plan['images']] or len(images) != len(plan['images']):
        raise ValueError('Embedded image verification failed')
    if item['data'].get('parentItem') != plan['parent_key'] or item['data'].get('linkMode') != 'imported_file':
        raise ValueError('Attachment is not an imported child of the expected parent')
    receipt = {'machine_name': machine_name(), 'parent_key': plan['parent_key'], 'attachment_key': item['key'],
               'attachment_path': str(path), 'html_sha256': digest(path), 'embedded_images_verified': len(images),
               'writeback_status': 'verified', 'cloud_sync_status': 'not_verified',
               'zotero_link': 'zotero://select/library/items/' + plan['parent_key']}
    write_json(plan_path.parent / 'zotero-sync-receipt.json', receipt)
    manifest = read_json(plan['manifest'])
    manifest['zotero'] = {**manifest.get('zotero', {}), **receipt}
    manifest['delivery_mode'] = 'zotero_attachment'
    write_json(plan['manifest'], manifest)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--manifest', type=Path, required=True)
    prep.set_defaults(action=prepare)
    check = sub.add_parser('verify')
    check.add_argument('--plan', type=Path, required=True)
    check.set_defaults(action=verify)
    args = parser.parse_args()
    try:
        print(json.dumps(args.action(args), ensure_ascii=False, indent=2))
    except (OSError, ValueError, ImportError, KeyError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
