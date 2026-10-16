"""Exercise real Git commits and rollback against isolated installed-skill fixtures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('versions', Path(__file__).resolve().parents[2] / 'scripts' / 'skill_versions.py')
versions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(versions)


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.live = self.base / 'installed'
        self.live.mkdir()
        (self.live / 'SKILL.md').write_text('version one\n')
        (self.live / '.git').mkdir()
        (self.live / '.git' / 'sentinel').write_text('preserve original history')
        (self.repo / 'local-sources.json').write_text(json.dumps({'sources': [
            {'path': str(self.live), 'destination': 'skills/example'}]}))
        self.root_patch = patch.object(versions, 'ROOT', self.repo)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Version Test')
        self.git('config', 'user.email', 'versions@example.invalid')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        versions.snapshot()
        self.git('add', 'skills', 'inventory.json')
        self.git('commit', '-m', 'fixture version')
        return self.git('rev-parse', 'HEAD')

    def test_snapshot_hashes_and_excludes_nested_git(self):
        versions.snapshot()
        self.assertFalse((self.repo / 'skills/example/.git').exists())
        manifest = json.loads((self.repo / 'inventory.json').read_text())
        self.assertEqual(manifest['skills'], ['example'])
        self.assertIn('skills/example/SKILL.md', manifest['files'])

    def test_preview_and_real_rollback_preserve_git_and_backup(self):
        old = self.commit()
        (self.live / 'SKILL.md').write_text('version two\n')
        (self.live / 'new.py').write_text('print(2)\n')
        self.commit()
        versions.restore('example', old, False)
        self.assertEqual((self.live / 'SKILL.md').read_text(), 'version two\n')
        versions.restore('example', old, True)
        self.assertEqual((self.live / 'SKILL.md').read_text(), 'version one\n')
        self.assertFalse((self.live / 'new.py').exists())
        self.assertTrue((self.live / '.git/sentinel').is_file())
        backups = list((self.repo / '.local-backups').glob('*/example'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'SKILL.md').read_text(), 'version two\n')
        versions.snapshot()
        self.assertIn('SKILL.md', self.git('diff', '--name-only'))

    def test_snapshot_propagates_deleted_files(self):
        (self.live / 'old.txt').write_text('old')
        versions.snapshot()
        (self.live / 'old.txt').unlink()
        versions.snapshot()
        self.assertFalse((self.repo / 'skills/example/old.txt').exists())

    def test_missing_source_aborts_before_changes(self):
        self.commit()
        old = (self.repo / 'skills/example/SKILL.md').read_bytes()
        (self.live / 'SKILL.md').write_text('new')
        config = json.loads((self.repo / 'local-sources.json').read_text())
        config['sources'].append({'path': str(self.base / 'missing'), 'destination': 'skills/missing'})
        (self.repo / 'local-sources.json').write_text(json.dumps(config))
        with self.assertRaises(FileNotFoundError):
            versions.snapshot()
        self.assertEqual((self.repo / 'skills/example/SKILL.md').read_bytes(), old)

    def test_secret_blocks_snapshot_without_copying(self):
        (self.live / 'credentials.txt').write_text('ghp_' + 'A' * 40)
        with self.assertRaises(ValueError):
            versions.snapshot()
        self.assertFalse((self.repo / 'skills/example').exists())

    def test_traversal_and_missing_skill_ref_rejected(self):
        commit = self.commit()
        with self.assertRaises(ValueError):
            versions.safe_target(self.live, '../../outside')
        with self.assertRaises(ValueError):
            versions.historical_skill(commit, '../example')
        with self.assertRaises(ValueError):
            versions.historical_skill(commit, 'missing')

    def test_save_push_verifies_remote_and_does_not_commit_local_config(self):
        for name in ['tests', 'third_party', 'scripts', 'docs']:
            (self.repo / name).mkdir()
            (self.repo / name / 'example.txt').write_text('fixture')
        for name in ['README.md', 'sources.example.json', '.gitattributes']:
            (self.repo / name).write_text('fixture')
        (self.repo / '.gitignore').write_text('local-sources.json\n.local-backups/\n')
        remote = self.base / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        self.git('remote', 'add', 'origin', str(remote))
        versions.save('Initial snapshot', True)
        first = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.git('ls-remote', 'origin', 'refs/heads/main').split()[0], first)
        self.assertNotIn('local-sources.json', self.git('ls-files').splitlines())
        versions.save('Unchanged snapshot', True)
        self.assertEqual(first, self.git('rev-parse', 'HEAD'))


if __name__ == '__main__':
    unittest.main()
