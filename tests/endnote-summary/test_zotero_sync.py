"""Exercise paper matching, portable images, and saved-attachment verification."""
from pathlib import Path
import base64
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'skills' / 'endnote-summary'
spec = importlib.util.spec_from_file_location('zotero_sync', SKILL / 'scripts' / 'zotero_sync.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def record(key, title='Primary work', doi=''):
    return {'key': key, 'data': {'itemType': 'journalArticle', 'title': title, 'DOI': doi}}


class ParentMatchingTests(unittest.TestCase):
    def match(self, rows):
        with patch.object(sync, 'get', return_value=rows):
            return sync.candidates('Primary work', '10.1000/primary')

    def test_imported_pdf_title_without_doi_can_match_uniquely(self):
        self.assertEqual(self.match([record('ONE', '<PRIMARY Work.pdf>')])['key'], 'ONE')

    def test_duplicate_titles_require_resolution(self):
        with self.assertRaises(ValueError):
            self.match([record('ONE'), record('TWO')])

    def test_conflicting_doi_never_uses_same_title(self):
        with self.assertRaises(ValueError):
            self.match([record('ONE', doi='10.1000/other')])

    def test_no_matching_parent_does_not_create_a_record(self):
        with self.assertRaises(ValueError):
            self.match([])

    def test_notes_and_attachments_are_not_parent_candidates(self):
        item = record('ONE')
        item['data']['itemType'] = 'attachment'
        with self.assertRaises(ValueError):
            self.match([item])


@unittest.skipIf(sys.version_info < (3, 10), 'Standalone HTML renderer requires Python 3.10+')
class HtmlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'paper'
        self.root.mkdir()
        self.source = self.root / 'summary.md'

    def test_local_image_bytes_and_table_survive_embedding(self):
        image = self.root / 'figure.png'
        image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='))
        self.source.write_text('# Paper\n\n![原图](figure.png)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n', encoding='utf8')
        output, images = sync.make_html(self.source, 'Paper')
        self.assertIn('<table>', output)
        self.assertIn('data:image/png;base64,', output)
        self.assertNotIn('src="figure.png"', output)
        self.assertEqual(images[0]['sha256'], sync.digest(image))

    def test_image_cannot_escape_package(self):
        (self.root.parent / 'private.png').write_bytes(b'private')
        self.source.write_text('![x](../private.png)', encoding='utf8')
        with self.assertRaises(ValueError):
            sync.make_html(self.source, 'Paper')

    def test_remote_image_is_not_silently_fetched(self):
        self.source.write_text('![x](https://example.org/figure.png)', encoding='utf8')
        with self.assertRaises(ValueError):
            sync.make_html(self.source, 'Paper')


class SavedAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.md = self.root / 'summary.md'
        self.md.write_text('# Paper', encoding='utf8')
        self.html = self.root / 'summary.html'
        self.html.write_text('<html><body>Paper</body></html>', encoding='utf8')
        self.saved = self.root / 'imported.html'
        self.saved.write_bytes(self.html.read_bytes())
        self.manifest = self.root / 'paper.match.json'
        sync.write_json(self.manifest, {})
        self.plan = self.root / 'zotero-sync-plan.json'
        sync.write_json(self.plan, {'machine_name': sync.machine_name(), 'parent_key': 'PARENT',
            'markdown_path': str(self.md), 'markdown_sha256': sync.digest(self.md),
            'html_path': str(self.html), 'html_sha256': sync.digest(self.html),
            'images': [], 'manifest': str(self.manifest)})
        self.item = {'key': 'CHILD', 'data': {'contentType': 'text/html', 'parentItem': 'PARENT',
                                            'linkMode': 'imported_file'},
                     'links': {'enclosure': {'href': self.saved.as_uri()}}}

    def verify(self, rows):
        from argparse import Namespace
        with patch.object(sync, 'get', return_value=rows):
            return sync.verify(Namespace(plan=self.plan))

    def test_verified_import_does_not_claim_cloud_delivery(self):
        receipt = self.verify([self.item])
        self.assertEqual(receipt['writeback_status'], 'verified')
        self.assertEqual(receipt['cloud_sync_status'], 'not_verified')
        self.assertEqual(sync.read_json(self.manifest)['zotero']['attachment_key'], 'CHILD')

    def test_external_link_cannot_pass_import_verification(self):
        self.item['data']['linkMode'] = 'linked_file'
        with self.assertRaises(ValueError):
            self.verify([self.item])
        self.assertFalse((self.root / 'zotero-sync-receipt.json').exists())

    def test_wrong_parent_cannot_pass_verification(self):
        self.item['data']['parentItem'] = 'OTHER'
        with self.assertRaises(ValueError):
            self.verify([self.item])

    def test_changed_imported_file_does_not_mark_success(self):
        self.saved.write_text('corrupted', encoding='utf8')
        with self.assertRaises(ValueError):
            self.verify([self.item])


if __name__ == '__main__':
    unittest.main()
