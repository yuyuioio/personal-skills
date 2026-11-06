#!/usr/bin/env python3
"""Prepare a verified Zotero attachment plan, then verify native Zotero writes.

Uses official Zotero 10 local writes by default, with explicit legacy JavaScript
fallback only. Checks local PDFs and verifies Markdown/HTML plus image resources.
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


def probe(args):
    """Check actual local PDF files before attempting any new download."""
    parent = candidates(args.title, args.doi or '')
    rows = get('items/' + parent['key'] + '/children')
    files = []
    for item in rows:
        data = item['data']
        if data.get('deleted') or data.get('contentType') != 'application/pdf':
            continue
        row = {'attachment_key': item['key'], 'title': data.get('title', ''),
               'status': 'unchecked', 'path': '', 'pages': 0}
        try:
            path = attachment_path(item)
            row['path'] = str(path)
            if not path.is_file():
                row['status'] = 'missing'
            else:
                with path.open('rb') as stream:
                    signature = stream.read(1024)
                if b'%PDF-' not in signature:
                    raise ValueError('Local file does not have a PDF signature')
                from pypdf import PdfReader
                pdf = PdfReader(str(path))
                if not pdf.pages:
                    raise ValueError('PDF has no pages')
                first = pdf.pages[0].extract_text() or ''
                row.update(status='readable_pdf', pages=len(pdf.pages), sha256=digest(path),
                           first_page_text=first,
                           text_status='text_available' if first.strip() else 'ocr_or_visual_reading_required')
        except ImportError:
            raise  # Missing parser is a tool problem, not evidence of a bad PDF.
        except Exception as error:
            row.update(status='unreadable', error=str(error))
        files.append(row)
    result = {'machine_name': machine_name(), 'parent_key': parent['key'],
              'parent_title': parent['data']['title'], 'doi': parent['data'].get('DOI', ''),
              'files': files, 'usable_pdf_keys': [r['attachment_key'] for r in files if r['status'] == 'readable_pdf'],
              'next_step': 'Verify PDF identity/version and distinguish main text from SI, then read the existing main PDF; download main text only if no usable matching main PDF exists.'}
    if args.out:
        write_json(args.out, result)
    return result


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
const sameBytes = async (a, b) => {
  const x = await IOUtils.read(a), y = await IOUtils.read(b);
  return x.length === y.length && x.every((value, i) => value === y[i]);
};
const resourcePath = (base, relative) => {
  const parts = relative.split('/');
  if (!parts.length || parts.some(p => !p || p === '.' || p === '..' || /[:\\]/.test(p))) {
    throw new Error('Unsafe image resource path');
  }
  return OS.Path.join(base, ...parts);
};
// Check all source resources before changing the library.
for (const image of plan.images) {
  if (!await IOUtils.exists(resourcePath(OS.Path.dirname(plan.markdown_path), image.path))) {
    throw new Error('Markdown image source missing: ' + image.path);
  }
}
const savedFormats = {};
for (const spec of [
  {format: 'html', path: plan.html_path, type: 'text/html', title: plan.attachment_title},
  {format: 'markdown', path: plan.markdown_path, type: 'text/markdown', title: plan.markdown_attachment_title}
]) {
  let saved = null;
  for (const id of parent.getAttachments()) {
    const item = await Zotero.Items.getAsync(id);
    if (item.deleted || item.attachmentLinkMode !== Zotero.Attachments.LINK_MODE_IMPORTED_FILE) continue;
    const path = await item.getFilePathAsync();
    const correctType = item.attachmentContentType === spec.type ||
      (spec.format === 'markdown' && path && /\.md$/i.test(path));
    if (correctType && path && await IOUtils.exists(path) && await sameBytes(path, spec.path)) {
      saved = item; break;
    }
  }
  const reused = !!saved;
  // importFromFile manages its own transaction; do not nest another transaction.
    if (!saved) saved = await Zotero.Attachments.importFromFile({
      file: spec.path, parentItemID: parent.id,
      title: spec.title, contentType: spec.type, charset: 'utf-8'
    });
    if (spec.format === 'markdown') {
      const directory = OS.Path.dirname(await saved.getFilePathAsync());
      for (const image of plan.images) {
        const source = resourcePath(OS.Path.dirname(plan.markdown_path), image.path);
        const target = resourcePath(directory, image.path);
        await IOUtils.makeDirectory(OS.Path.dirname(target), {createAncestors: true, ignoreExisting: true});
        if (await IOUtils.exists(target)) {
          if (!await sameBytes(source, target)) throw new Error('Existing Markdown resource differs: ' + image.path);
        } else {
          await Zotero.File.copyFile(source, target);
        }
      }
    }
  savedFormats[spec.format] = {status: reused ? 'already_present' : 'saved',
    attachment_key: saved.key, attachment_path: await saved.getFilePathAsync()};
}
const result = {machine_name: machine, parent_key: parent.key, parent_id: parent.id,
  attachments: savedFormats, attachment_key: savedFormats.html.attachment_key,
  attachment_path: savedFormats.html.attachment_path, markdown_sha256: plan.markdown_sha256};
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
            try:
                path = attachment_path(item)
            except (OSError, ValueError):
                continue  # An unavailable old attachment must not block delivery.
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
            'required_formats': ['html', 'markdown'],
            'markdown_attachment_title': '中文逐图总结（Markdown） · ' + (doi or bib['title']),
            'native_result_path': str(root / 'zotero-native-result.json')}
    write_json(root / 'zotero-sync-plan.json', plan)
    if getattr(args, 'legacy_script', False):
        (root / 'zotero-attach.js').write_text(NATIVE.replace('__PLAN__', json.dumps(plan, ensure_ascii=False)), encoding='utf-8')
    manifest['delivery_mode'] = 'zotero_attachment'
    manifest['zotero'] = {'machine_name': machine_name(), 'parent_key': parent['key'], 'match_evidence': evidence,
                          'writeback_status': 'prepared', 'cloud_sync_status': 'not_verified'}
    manifest['outputs']['zotero_html'] = str(html_path)
    manifest['outputs']['zotero_markdown'] = str(source)
    write_json(manifest_path, manifest)
    return {'plan': str(root / 'zotero-sync-plan.json'), 'native_script': str(root / 'zotero-attach.js') if getattr(args, 'legacy_script', False) else None,
            'parent_key': parent['key'], 'match_evidence': evidence, 'embedded_images': len(images),
            'machine_name': machine_name(), 'required_formats': plan['required_formats'],
            'html_bytes': html_path.stat().st_size}


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
    formats = {'html': {'attachment_key': item['key'], 'attachment_path': str(path),
                        'sha256': digest(path), 'writeback_status': 'verified'}}
    if 'markdown' in plan.get('required_formats', []):
        md_matches = []
        for candidate in children:
            data = candidate['data']
            if data.get('deleted') or data.get('contentType') not in ('text/markdown', 'text/plain', 'application/octet-stream'):
                continue
            md_path = attachment_path(candidate)
            if md_path.suffix.casefold() == '.md' and md_path.is_file() and digest(md_path) == plan['markdown_sha256']:
                md_matches.append((candidate, md_path))
        if len(md_matches) != 1:
            raise ValueError('Expected exactly one byte-identical Markdown attachment; found ' + str(len(md_matches)))
        md_item, md_path = md_matches[0]
        if md_item['data'].get('parentItem') != plan['parent_key'] or md_item['data'].get('linkMode') != 'imported_file':
            raise ValueError('Markdown is not an imported child of the expected parent')
        for resource in plan['images']:
            image_path = (md_path.parent / resource['path']).resolve()
            if not image_path.is_relative_to(md_path.parent.resolve()):
                raise ValueError('Markdown image escapes attachment directory')
            if not image_path.is_file() or digest(image_path) != resource['sha256']:
                raise ValueError('Markdown image missing or changed: ' + resource['path'])
        formats['markdown'] = {'attachment_key': md_item['key'], 'attachment_path': str(md_path),
                               'sha256': digest(md_path), 'images_verified': len(plan['images']),
                               'writeback_status': 'verified'}
    receipt = {'machine_name': machine_name(), 'parent_key': plan['parent_key'], 'attachment_key': item['key'],
               'attachment_path': str(path), 'html_sha256': digest(path), 'embedded_images_verified': len(images),
               'writeback_status': 'verified', 'cloud_sync_status': 'not_verified',
               'zotero_link': 'zotero://select/library/items/' + plan['parent_key']}
    receipt['attachments'] = formats
    write_json(plan_path.parent / 'zotero-sync-receipt.json', receipt)
    manifest = read_json(plan['manifest'])
    manifest['zotero'] = {**manifest.get('zotero', {}), **receipt}
    manifest['delivery_mode'] = 'zotero_attachment'
    write_json(plan['manifest'], manifest)
    return receipt


def save(args):
    """Save through the official loopback API; never open Run JavaScript."""
    from zotero_local_api import Client
    if args.manifest:
        prepared = prepare(args)
        plan_path = Path(prepared['plan'])
    else:
        plan_path = args.plan.resolve(strict=True)
    plan = read_json(plan_path)
    if machine_name().casefold() != plan['machine_name'].casefold():
        raise ValueError('Computer changed; prepare a new plan')
    if digest(Path(plan['markdown_path'])) != plan['markdown_sha256'] or digest(Path(plan['html_path'])) != plan['html_sha256']:
        raise ValueError('Source files changed since preparation')
    client = Client()
    client.connect()
    # Validate source resources before adding either attachment.
    for image in plan['images']:
        resource = (Path(plan['markdown_path']).parent / image['path']).resolve()
        if not resource.is_relative_to(Path(plan['markdown_path']).parent.resolve()) or digest(resource) != image['sha256']:
            raise ValueError('Markdown image source missing or changed: ' + image['path'])
    result = client.attach_file(parent_key=plan['parent_key'], parent_title=plan['parent_title'], doi=plan['doi'],
                              path=plan['html_path'], title=plan['attachment_title'],
                              receipt_path=plan_path.parent / 'zotero-api-result.json')
    results = {'html': result}
    if 'markdown' in plan.get('required_formats', []):
        md_result = client.attach_file(parent_key=plan['parent_key'], parent_title=plan['parent_title'], doi=plan['doi'],
                                     path=plan['markdown_path'], title=plan['markdown_attachment_title'],
                                     receipt_path=plan_path.parent / 'zotero-api-markdown-result.json')
        results['markdown'] = md_result
        md_root = Path(md_result['attachment_path']).resolve(strict=True).parent
        import shutil
        for image in plan['images']:
            source = (Path(plan['markdown_path']).parent / image['path']).resolve(strict=True)
            target = (md_root / image['path']).resolve()
            if not target.is_relative_to(md_root):
                raise ValueError('Markdown resource escapes the registered attachment')
            if target.exists():
                if not target.is_file() or digest(target) != image['sha256']:
                    raise ValueError('Existing Markdown resource differs: ' + image['path'])
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        # Only the dual-format verifier below may mark the entire delivery complete.
        md_result['resources_copied'] = len(plan['images'])
    receipt = verify(argparse.Namespace(plan=plan_path))
    receipt['transport'] = 'official_local_api'
    receipt['save_status'] = {kind: value['status'] for kind, value in results.items()}
    write_json(plan_path.parent / 'zotero-sync-receipt.json', receipt)
    manifest = read_json(plan['manifest'])
    manifest['zotero'] = {**manifest.get('zotero', {}), **receipt}
    write_json(plan['manifest'], manifest)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('probe', help='Check existing local Zotero PDFs before downloading')
    inspect.add_argument('--title', required=True)
    inspect.add_argument('--doi', default='')
    inspect.add_argument('--out', type=Path)
    inspect.set_defaults(action=probe)
    prep = sub.add_parser('prepare')
    prep.add_argument('--manifest', type=Path, required=True)
    prep.add_argument('--legacy-script', action='store_true', help='Explicit fallback only; not needed with configured Zotero 10')
    prep.set_defaults(action=prepare)
    writer = sub.add_parser('save', help='Save and verify both formats via official Zotero 10 local API')
    target = writer.add_mutually_exclusive_group(required=True)
    target.add_argument('--manifest', type=Path)
    target.add_argument('--plan', type=Path)
    writer.set_defaults(action=save)
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
