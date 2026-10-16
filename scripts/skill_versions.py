"""Snapshot installed skills; preview or restore one skill from a Git commit."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.venv', '__pycache__', 'node_modules', '.local-backups'}
SECRET = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-proj-[A-Za-z0-9_-]{25,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def git(*args, binary=False):
    result = subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout if binary else result.stdout.decode('utf-8').strip()


def local_sources():
    config = ROOT / 'local-sources.json'
    if not config.is_file():
        raise ValueError('Missing local-sources.json; copy sources.example.json and edit paths first.')
    entries = json.loads(config.read_text(encoding='utf-8'))['sources']
    seen = set()
    for entry in entries:
        rel = PurePosixPath(entry['destination'])
        if rel.is_absolute() or '..' in rel.parts or '\\' in str(rel) or ':' in str(rel):
            raise ValueError('Unsafe destination path')
        if len(rel.parts) != 2 or rel.parts[0] not in {'skills', 'tests', 'third_party'}:
            raise ValueError('Destination must be skills/name, tests/name, or third_party/name')
        if str(rel) in seen:
            raise ValueError('Duplicate destination')
        seen.add(str(rel))
        entry['path'] = Path(entry['path']).resolve(strict=True)
        if rel.parts[0] == 'skills' and not (entry['path'] / 'SKILL.md').is_file():
            raise ValueError(f'Missing SKILL.md: {entry["path"]}')
    return entries


def files_under(folder):
    if folder.is_file():
        return {folder.name: folder.read_bytes()}
    found = {}
    for parent, dirs, files in os.walk(folder, followlinks=False):
        for name in list(dirs):
            p = Path(parent) / name
            if name in EXCLUDED:
                dirs.remove(name)
            elif p.is_symlink() or p.is_junction():
                raise ValueError(f'Nested link requires explicit review: {p}')
        for name in files:
            p = Path(parent) / name
            if name.endswith(('.pyc', '.pyo', '.log')) or name == '.env' or name.startswith('.env.'):
                continue
            if p.is_symlink():
                raise ValueError(f'File link requires explicit review: {p}')
            data = p.read_bytes()
            if SECRET.search(data):
                raise ValueError(f'Possible credential found; refusing snapshot: {p}')
            found[p.relative_to(folder).as_posix()] = data
    return found


def safe_target(folder, rel):
    relative = PurePosixPath(rel)
    if relative.is_absolute() or '..' in relative.parts or '\\' in rel or ':' in rel:
        raise ValueError('Unsafe file path')
    target = folder.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(folder.resolve()):
        raise ValueError('Target escapes destination')
    current = target
    while current != folder:
        if current.is_symlink() or current.is_junction():
            raise ValueError(f'Refusing to write through link: {current}')
        current = current.parent
    return target


def mirror(folder, desired, removable):
    folder.mkdir(parents=True, exist_ok=True)
    for rel in sorted(set(removable) - set(desired)):
        target = safe_target(folder, rel)
        if target.is_file():
            target.unlink()
    for rel, data in desired.items():
        target = safe_target(folder, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)


def snapshot():
    # Read every source before touching the repository, so missing paths abort early.
    prepared = [(entry, files_under(entry['path'])) for entry in local_sources()]
    inventory = {'format': 1, 'skills': [], 'files': {}}
    for entry, data in prepared:
        destination = entry['destination']
        folder = ROOT / destination
        old = files_under(folder) if folder.exists() else {}
        mirror(folder, data, old)
        if destination.startswith('skills/'):
            inventory['skills'].append(destination.split('/')[1])
        for rel, content in data.items():
            inventory['files'][destination + '/' + rel] = hashlib.sha256(content).hexdigest()
    (ROOT / 'inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Snapshotted {len(inventory["skills"])} skills, {len(inventory["files"])} files.')


def save(message, push):
    if not message.strip():
        raise ValueError('A meaningful version message is required')
    snapshot()
    git('add', '--', 'skills', 'tests', 'third_party', 'inventory.json', 'scripts', 'docs',
        'README.md', 'sources.example.json', '.gitignore', '.gitattributes')
    if git('diff', '--cached', '--name-only'):
        print(git('commit', '-m', message))
    else:
        print('No content changes; no new commit needed.')
    if push:
        git('push', '-u', 'origin', 'main')
        local = git('rev-parse', 'HEAD')
        remote = git('ls-remote', 'origin', 'refs/heads/main').split()[0]
        if local != remote:
            raise ValueError('Local and remote commit do not match')
        print('GitHub verified: ' + local)


def historical_skill(ref, skill):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', skill):
        raise ValueError('Invalid skill name')
    commit = git('rev-parse', '--verify', '--end-of-options', ref + '^{commit}')
    prefix = f'skills/{skill}/'
    names = git('ls-tree', '-r', '--name-only', commit, '--', prefix).splitlines()
    data = {name[len(prefix):]: git('show', f'{commit}:{name}', binary=True) for name in names}
    if 'SKILL.md' not in data:
        raise ValueError('That commit does not contain the selected skill')
    return commit, data


def restore(skill, ref, apply):
    entries = {e['destination']: e for e in local_sources()}
    entry = entries.get('skills/' + skill)
    if entry is None:
        raise ValueError('Skill is not configured on this computer')
    commit, desired = historical_skill(ref, skill)
    live = entry['path']
    current = files_under(live)
    changed = sorted(k for k in set(current) | set(desired) if current.get(k) != desired.get(k))
    print(f'{skill} -> {commit[:12]}: {len(changed)} changed files')
    for name in changed:
        print('  ' + name)
    if not apply:
        print('Preview only. Add --apply to back up and restore the installed skill.')
        return
    if not changed:
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    backup = ROOT / '.local-backups' / stamp / skill
    # Full filesystem backup (including ignored files and any existing .git).
    shutil.copytree(live, backup, symlinks=True)
    mirror(live, desired, current)
    if files_under(live) != desired:
        raise ValueError(f'Restore verification failed; backup: {backup}')
    print('Restored and verified. Previous files saved at: ' + str(backup))
    print('Run save -m "Restore ' + skill + ' to ' + commit[:12] + '" --push to record the rollback.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('snapshot')
    sub.add_parser('status')
    sub.add_parser('history')
    s = sub.add_parser('save')
    s.add_argument('-m', '--message', required=True)
    s.add_argument('--push', action='store_true')
    r = sub.add_parser('restore')
    r.add_argument('--skill', required=True)
    r.add_argument('--ref', required=True)
    r.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.command == 'snapshot':
        snapshot()
    elif args.command == 'save':
        save(args.message, args.push)
    elif args.command == 'restore':
        restore(args.skill, args.ref, args.apply)
    elif args.command == 'history':
        print(git('log', '-20', '--date=iso-local', '--format=%h %ad %s'))
    else:
        for entry in local_sources():
            if not entry['destination'].startswith('skills/'):
                continue
            live = files_under(entry['path'])
            backed = files_under(ROOT / entry['destination'])
            changes = sum(live.get(k) != backed.get(k) for k in set(live) | set(backed))
            print(f'{entry["destination"]}: {changes} file differences')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.decode('utf-8', errors='replace'), file=sys.stderr)
        sys.exit(1)
