"""Publish the local personal-skills repository to its configured GitHub branch."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from skill_versions import ROOT, SECRET, git, safe_target

REMOTE = 'https://github.com/yuyuioio/personal-skills.git'
BRANCH = 'refs/heads/main'


def local_skill_inventory():
    manifest = ROOT / 'inventory.json'
    original = json.loads(manifest.read_text(encoding='utf-8'))
    scopes = ['skills/' + name for name in original['skills']]
    if not scopes or len(scopes) != len(set(scopes)):
        raise ValueError('The backup scope must list distinct local skills')
    for scope in scopes:
        if scope.count('/') != 1 or not safe_target(ROOT, scope + '/SKILL.md').is_file():
            raise ValueError(f'Missing or invalid skill source: {scope}')

    file_list = git('ls-files', '-z', '--cached', '--others', '--exclude-standard', '--',
                    *scopes, binary=True)
    updated = {path: digest for path, digest in original['files'].items()
               if not any(path.startswith(scope + '/') for scope in scopes)}
    for path in dict.fromkeys(file_list.decode('utf-8').split('\0')):
        if not path:
            continue
        target = safe_target(ROOT, path)
        if not target.exists():
            continue  # A tracked deletion is recorded in the next snapshot.
        raw = target.read_bytes()
        if SECRET.search(raw):
            raise ValueError(f'Possible credential in skill file: {path}')
        updated[path] = hashlib.sha256(raw).hexdigest()
    return manifest, original, dict(original, files=dict(sorted(updated.items()))), scopes


def publish_local(check_only):
    if git('symbolic-ref', 'HEAD') != BRANCH:
        raise ValueError('The local repository must be on main')
    if git('remote', 'get-url', '--push', '--all', 'origin').splitlines() != [REMOTE]:
        raise ValueError('The configured destination does not match the personal-skills repository')

    manifest, original, updated, scopes = local_skill_inventory()
    dirty = git('status', '--porcelain=v1', '--untracked-files=all', '--', *scopes, 'inventory.json')
    if check_only:
        print(f'Checked {len(scopes)} local skills. Snapshot changes: {bool(dirty or updated != original)}')
        return

    if dirty or updated != original:
        if git('diff', '--cached', '--name-only'):
            raise ValueError('A local commit is already staged. Finish it before the next backup.')
        if updated != original:
            manifest.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        git('add', '-A', '--', *scopes, 'inventory.json')
        if git('diff', '--cached', '--name-only'):
            message = f"Back up local skills ({datetime.now().astimezone():%Y-%m-%d %H:%M %z})"
            print(git('commit', '-m', message))

    # An ordinary push refuses to overwrite a remote branch that has diverged.
    os.environ['GIT_TERMINAL_PROMPT'] = '0'
    os.environ['GCM_INTERACTIVE'] = 'Never'
    git('-c', 'remote.origin.mirror=false', '-c', 'push.followTags=false',
        'push', '--no-force', '--no-follow-tags', '--recurse-submodules=no',
        'origin', f'{BRANCH}:{BRANCH}')
    local = git('rev-parse', BRANCH)
    remote = git('ls-remote', '--exit-code', REMOTE, BRANCH).split()[0]
    if remote != local:
        raise ValueError('GitHub branch does not match the local snapshot')
    print(f'GitHub verified: {local}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate local inputs without writing or uploading')
    args = parser.parse_args()
    try:
        publish_local(args.check)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Backup stopped: {exc}', file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.decode('utf-8', errors='replace').strip(), file=sys.stderr)
        sys.exit(1)
