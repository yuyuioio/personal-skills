#!/usr/bin/env python3
"""Attachment-only client for Zotero 10's official loopback write API.

No generic write, delete, remote server, or SQLite interface is exposed.
The persistent local key is encrypted with Windows DPAPI for the current user.
"""
from __future__ import annotations
import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import platform
import re
import sys
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse, unquote
from urllib.request import Request, build_opener, ProxyHandler

BASE = 'http://127.0.0.1:23119/api/'
APP_NAME = 'Codex endnote-summary attachment writer'
CONFIG = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CodexZotero' / 'local-api.json'
HTTP = build_opener(ProxyHandler({}))

def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def normal_title(value):
    import html
    value = html.unescape(unicodedata.normalize('NFKC', value))
    value = re.sub(r'</?(?:i|b|em|strong|sub|sup)>', '', value, flags=re.I)
    value = re.sub(r'\.pdf\s*$', '', value, flags=re.I)
    return ''.join(c for c in value.casefold() if c.isalnum())

def normal_doi(value):
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.I).casefold()

class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

def dpapi(data: bytes, decrypt=False):
    if os.name != 'nt': raise ValueError('This credential store requires Windows DPAPI')
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), 'Codex Zotero local API', None, None, None, 1, ctypes.byref(target))
    if not ok: raise ctypes.WinError(ctypes.get_last_error())
    try: return ctypes.string_at(target.pbData, target.cbData)
    finally: kernel.LocalFree(target.pbData)

def save_json(path, obj):
    path = Path(path)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

class Client:
    def __init__(self, config_path=CONFIG):
        self.config_path = Path(config_path)
        self.server_id = None
        self.key = None

    def request(self, method, route, *, obj=None, form=None, raw=None, headers=None, write=False, timeout=60):
        # Never transmit credentials or upload capabilities to another origin.
        if route.startswith('http'):
            u = urlparse(route)
            if u.scheme != 'http' or u.hostname != '127.0.0.1' or u.port != 23119 or not u.path.startswith('/api/local/uploads/'):
                raise ValueError('Upload endpoint is not this Zotero loopback server')
            url = route
        else:
            if route.startswith('/') or '..' in route.split('/'): raise ValueError('Invalid API route')
            url = BASE + route
        hs = {'Zotero-API-Version': '3', **(headers or {})}
        if self.server_id: hs['Zotero-Server-ID'] = self.server_id
        if write:
            if not self.key: raise ValueError('Run configure once before writing attachments')
            hs['Zotero-API-Key'] = self.key
        if obj is not None:
            raw = json.dumps(obj, ensure_ascii=False).encode('utf-8'); hs['Content-Type'] = 'application/json'
        elif form is not None:
            raw = urlencode(form).encode(); hs['Content-Type'] = 'application/x-www-form-urlencoded'
        try:
            with HTTP.open(Request(url, data=raw, headers=hs, method=method), timeout=timeout) as r:
                data = r.read()
                return r.status, dict(r.headers), (json.loads(data) if 'application/json' in r.headers.get('Content-Type', '') else data)
        except HTTPError as e:
            # Do not print request headers, API keys, or capability URLs.
            body = e.read().decode('utf-8', 'replace')[:1000]
            raise ValueError(f'Zotero HTTP {e.code}: {body}. No automatic authorization or write retry.') from None

    def connect(self):
        _, headers, _ = self.request('GET', '')
        sid = headers.get('Zotero-Server-ID')
        if not sid: raise ValueError('Zotero 10+ server identity header is missing')
        self.server_id = sid
        version = headers.get('X-Zotero-Version', '')
        if self.config_path.exists():
            cfg = json.loads(self.config_path.read_text(encoding='utf-8'))
            if cfg['machine_name'].casefold() != platform.node().casefold(): raise ValueError('Credential belongs to another computer')
            if cfg['server_id'] != sid: raise ValueError('Zotero database changed; configure explicitly for the new database')
            self.key = dpapi(base64.b64decode(cfg['key_dpapi']), decrypt=True).decode('ascii')
        return {'machine_name': platform.node(), 'zotero_version': version, 'server_id': sid, 'configured': bool(self.key), 'credential_protection': 'Windows DPAPI CurrentUser'}

    def configure(self):
        status = self.connect()
        if self.key: return {**status, 'status': 'already_configured'}
        print('Waiting for Zotero official authorization dialog: ' + APP_NAME, flush=True)
        _, _, auth = self.request('POST', 'local/authorize', obj={'appName': APP_NAME}, timeout=180)
        if not auth.get('remember'): raise ValueError('Persistent setup requires Always Allow; no single-use key was saved')
        cfg = {'machine_name': platform.node(), 'server_id': self.server_id, 'app_name': APP_NAME, 'remember': True,
               'key_dpapi': base64.b64encode(dpapi(auth['key'].encode('ascii'))).decode('ascii')}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        save_json(self.config_path, cfg)
        self.key = auth['key']
        return {**status, 'configured': True, 'status': 'configured', 'config_path': str(self.config_path)}

    def get(self, route): return self.request('GET', route)[2]

    def validate_parent(self, key, title, doi):
        if not re.fullmatch('[A-Z0-9]{8}', key): raise ValueError('Invalid parent item key')
        row = self.get('users/0/items/' + key)
        data = row['data']
        if data.get('deleted') or data['itemType'] in ('note', 'attachment', 'annotation'): raise ValueError('Expected an existing regular parent item')
        if not title or normal_title(data.get('title', '')) != normal_title(title): raise ValueError('Parent title does not match')
        actual = normal_doi(data.get('DOI', ''))
        if doi and actual and actual != normal_doi(doi): raise ValueError('Parent DOI conflicts')
        return row

    def attachment_path(self, row):
        url = row.get('links', {}).get('enclosure', {}).get('href')
        if not url:
            url = self.get('users/0/items/' + row['key'] + '/file/view/url')
            if isinstance(url, bytes): url = url.decode('utf-8')
            if isinstance(url, dict): url = url.get('url', '')
        u = urlparse(url)
        if u.scheme != 'file' or u.netloc not in ('', 'localhost'): raise ValueError('Expected a local file attachment')
        value = unquote(u.path)
        if re.match(r'^/[A-Za-z]:/', value): value = value[1:]
        return Path(value)

    def attach_file(self, *, parent_key, parent_title, doi, path, title, receipt_path=None):
        path = Path(path).resolve(strict=True)
        if not path.is_file(): raise ValueError('Source is not a regular file')
        if path.stat().st_size > 250 * 1024 * 1024: raise ValueError('Attachment is above this client\'s 250 MiB limit')
        self.validate_parent(parent_key, parent_title, doi)
        fingerprint = digest(path)
        content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        receipt_path = Path(receipt_path or path.with_name(path.name + '.zotero-receipt.json'))
        rows = self.get('users/0/items/' + parent_key + '/children')
        matches = []
        for row in rows:
            d = row['data']
            if d.get('itemType') != 'attachment' or d.get('deleted') or d.get('linkMode') != 'imported_file': continue
            if d.get('contentType') != content_type: continue
            try:
                local = self.attachment_path(row)
                if local.is_file() and digest(local) == fingerprint: matches.append((row, local))
            except ValueError: continue
        if len(matches) > 1: raise ValueError('More than one identical attachment exists; not adding another')
        if matches:
            row, local = matches[0]
            result = {'status': 'already_present', 'machine_name': platform.node(), 'parent_key': parent_key, 'attachment_key': row['key'], 'sha256': fingerprint, 'attachment_path': str(local), 'writeback_status': 'verified', 'cloud_sync_status': 'not_verified', 'transport': 'official_local_api'}
            save_json(receipt_path, result); return result
        if not self.key: raise ValueError('Run configure once before writing attachments')
        # Recovery journal prevents a failed upload from creating new empty items on retry.
        journal_path = receipt_path.with_suffix(receipt_path.suffix + '.pending.json')
        if journal_path.exists():
            journal = json.loads(journal_path.read_text(encoding='utf-8'))
            if any(journal.get(k) != v for k, v in [('server_id', self.server_id), ('parent_key', parent_key), ('sha256', fingerprint)]): raise ValueError('Pending write belongs to another attachment')
            item_key = journal['attachment_key']
            existing = self.get('users/0/items/' + item_key)
            if existing['data'].get('parentItem') != parent_key or existing['data'].get('linkMode') != 'imported_file': raise ValueError('Pending attachment identity changed')
        else:
            # This Zotero 10 build does not expose the web API's /items/new route.
            # Use its documented imported_file schema; never create a main record.
            template = {'itemType': 'attachment', 'linkMode': 'imported_file', 'tags': [], 'relations': {},
                        'note': '', 'charset': 'utf-8' if content_type.startswith('text/') else ''}
            template.update(parentItem=parent_key, title=title, filename=path.name, contentType=content_type)
            _, _, out = self.request('POST', 'users/0/items', obj=[template], write=True,
                                    headers={'Zotero-Write-Token': hashlib.sha256((parent_key + ':' + fingerprint).encode()).hexdigest()[:32]})
            if out.get('failed'): raise ValueError('Attachment creation failed: ' + json.dumps(out['failed'], ensure_ascii=False))
            created = out.get('successful', {}).get('0') or out.get('success', {}).get('0')
            item_key = created['key'] if isinstance(created, dict) else created
            if not item_key: raise ValueError('Zotero did not return a created attachment key; inspect children before retrying')
            save_json(journal_path, {'server_id': self.server_id, 'parent_key': parent_key, 'sha256': fingerprint, 'attachment_key': item_key})
        endpoint = 'users/0/items/' + item_key + '/file'
        params = {'md5': digest(path, 'md5'), 'filename': path.name, 'filesize': path.stat().st_size,
                  'mtime': int(path.stat().st_mtime * 1000), 'contentType': content_type}
        precondition = {'If-None-Match': '*'}
        _, _, upload = self.request('POST', endpoint, form=params, headers=precondition, write=True)
        if not upload.get('exists'):
            if upload.get('prefix') or upload.get('suffix'): raise ValueError('Unexpected remote-style upload envelope')
            status, _, _ = self.request('POST', upload['url'], raw=path.read_bytes(), headers={'Content-Type': upload['contentType']})
            if status != 201: raise ValueError('Upload did not return 201')
            status, _, _ = self.request('POST', endpoint, form={'upload': upload['uploadKey']}, headers=precondition, write=True)
            if status != 204: raise ValueError('Upload registration did not return 204')
        row = self.get('users/0/items/' + item_key)
        local = self.attachment_path(row)
        if row['data'].get('parentItem') != parent_key or row['data'].get('linkMode') != 'imported_file' or not local.is_file() or digest(local) != fingerprint:
            raise ValueError('Saved attachment verification failed; inspect pending journal, do not create another')
        result = {'status': 'saved', 'machine_name': platform.node(), 'parent_key': parent_key, 'attachment_key': item_key, 'sha256': fingerprint, 'attachment_path': str(local), 'writeback_status': 'verified', 'cloud_sync_status': 'not_verified', 'transport': 'official_local_api'}
        save_json(receipt_path, result)
        journal_path.unlink(missing_ok=True)
        return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('configure'); sub.add_parser('status')
    attach = sub.add_parser('attach')
    attach.add_argument('--parent-key', required=True); attach.add_argument('--parent-title', required=True)
    attach.add_argument('--doi', default=''); attach.add_argument('--file', type=Path, required=True)
    attach.add_argument('--title', required=True); attach.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    try:
        c = Client()
        if args.command == 'configure': out = c.configure()
        else:
            out = c.connect()
            if args.command == 'attach': out = c.attach_file(parent_key=args.parent_key, parent_title=args.parent_title, doi=args.doi, path=args.file, title=args.title, receipt_path=args.receipt)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as e: parser.exit(1, str(e) + '\n')

if __name__ == '__main__': main()
