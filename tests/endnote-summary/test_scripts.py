"""Guard against incorrect DOI/record association and unsafe writeback claims."""
from pathlib import Path
import importlib.util
import json
import tempfile
import unittest
import sys
import io
from contextlib import redirect_stdout
from html import escape
from argparse import Namespace

SKILL_ROOT = Path(__file__).resolve().parents[2] / 'skills' / 'endnote-summary'
spec = importlib.util.spec_from_file_location('paper_bundle', SKILL_ROOT / 'scripts' / 'paper_bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)
sys.modules['paper_bundle'] = bundle
spec_wb = importlib.util.spec_from_file_location('endnote_writeback', SKILL_ROOT / 'scripts' / 'endnote_writeback.py')
writeback = importlib.util.module_from_spec(spec_wb)
spec_wb.loader.exec_module(writeback)


class MatchingTests(unittest.TestCase):
    def manifest(self, doi='10.1000/primary'):
        return {'bibliography': {'doi': doi, 'doi_status': 'verified', 'title': 'Primary work'},
                'source_pdf': {'sha256': 'unknown'}}

    def record(self, number, doi='10.1000/primary'):
        return {'record_number': number, 'doi': doi, 'title': 'Primary work',
                'authors': [], 'year': '2026', 'attachments': []}

    def test_doi_normalization_preserves_balanced_suffix(self):
        self.assertEqual(bundle.normalize_doi('https://doi.org/10.1000/ABC(1).'), '10.1000/abc(1)')
        self.assertEqual(bundle.normalize_doi('doi: 10.1000/abc).'), '10.1000/abc')
        self.assertEqual(bundle.normalize_doi('no DOI'), '')

    def test_primary_and_cited_doi_both_remain_candidates(self):
        candidates = bundle.collect_dois(['DOI: 10.1000/primary\nReferences 10.1000/cited'], {})
        self.assertEqual({c['doi'] for c in candidates}, {'10.1000/primary', '10.1000/cited'})

    def test_metadata_doi_excludes_dictionary_quotes(self):
        candidates = bundle.collect_dois([], {'/Subject': '10.1000/primary'})
        self.assertEqual(candidates[0]['doi'], '10.1000/primary')

    def test_duplicate_doi_records_never_select_first(self):
        result = bundle.match_records(self.manifest(), [self.record('1'), self.record('2')], 'library.enl')
        self.assertEqual(result['status'], 'ambiguous')
        self.assertIsNone(result['record_number'])

    def test_record_requires_library_scope(self):
        result = bundle.match_records(self.manifest(), [self.record('1')], '')
        self.assertEqual(result['status'], 'review_required')
        self.assertIsNone(result['record_number'])

    def test_candidate_doi_does_not_trigger_strong_match(self):
        manifest = self.manifest()
        manifest['bibliography']['doi_status'] = 'candidate'
        result = bundle.match_records(manifest, [self.record('1')], 'library.enl')
        self.assertEqual(result['status'], 'review_required')

    def test_matched_is_not_attached(self):
        result = bundle.match_records(self.manifest(), [self.record('1')], 'library.enl')
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['writeback_status'], 'not_attempted')

    def test_conflicting_hash_and_doi_requires_review(self):
        with tempfile.TemporaryDirectory() as folder:
            pdf = Path(folder) / 'a.pdf'
            pdf.write_bytes(b'fixture')
            manifest = self.manifest()
            manifest['source_pdf']['sha256'] = bundle.digest(pdf)
            record = self.record('1', '10.1000/other')
            record['attachments'] = [str(pdf)]
            result = bundle.match_records(manifest, [record], 'library.enl')
            self.assertEqual(result['status'], 'ambiguous')

    def test_internal_attachment_cannot_escape_library(self):
        self.assertIsNone(bundle.attachment_path('internal-pdf://../../../private.pdf', 'library.enl'))
        self.assertIsNone(bundle.attachment_path('file://remote-host/share/file.pdf', 'library.enl'))

    def test_verified_doi_requires_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bib.json'
            path.write_text(json.dumps({'doi': '10.1000/primary', 'doi_status': 'verified'}))
            with self.assertRaises(ValueError):
                bundle.read_bibliography(path)

    def test_xml_richtext_and_local_reference_number(self):
        xml = '<xml><records><record><rec-number>7</rec-number><titles><title><style>Paper</style></title></titles><electronic-resource-num><style>10.1000/primary</style></electronic-resource-num></record></records></xml>'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'export.xml'
            path.write_text(xml)
            record = bundle.load_xml(path)[0]
            self.assertEqual(record['record_number'], '7')
            self.assertEqual(record['title'], 'Paper')
            self.assertEqual(record['doi'], '10.1000/primary')

    def test_xml_entities_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'export.xml'
            path.write_text('<!DOCTYPE xml [<!ENTITY a "x">]><xml/>')
            with self.assertRaises(ValueError):
                bundle.load_xml(path)

    def test_prepare_and_package_preserve_identity_without_claiming_attachment(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pdf = root / 'paper.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.add_metadata({'/Subject': 'DOI: 10.1000/primary'})
            with pdf.open('wb') as stream:
                writer.write(stream)
            bundle.prepare(Namespace(pdf=pdf, output_dir=root, bibliography=None,
                                     library=None, endnote_xml=None, overwrite=False))
            manifest_path = next(root.glob('*.match.json'))
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            self.assertEqual(manifest['bibliography']['doi'], '')
            self.assertEqual(manifest['summary_status'], 'pending')
            self.assertEqual(manifest['delivery_mode'], 'manual_attachment')
            self.assertEqual(manifest['endnote']['status'], 'not_checked')
            body = root / 'body.md'
            body.write_text('A real agent-written body', encoding='utf-8')
            # A blank PDF must not masquerade as a readable full paper.
            with self.assertRaises(ValueError):
                bundle.package(Namespace(manifest=manifest_path, body=body, notes=None, overwrite=False))
            manifest['extraction']['status'] = 'ocr_completed'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            bundle.package(Namespace(manifest=manifest_path, body=body, notes=None, overwrite=False))
            packaged = json.loads(manifest_path.read_text(encoding='utf-8'))
            summary = Path(packaged['outputs']['summary_markdown'])
            self.assertIn(manifest['source_pdf']['sha256'], summary.read_text(encoding='utf-8'))
            self.assertEqual(packaged['outputs']['summary_sha256'], bundle.digest(summary))
            self.assertEqual(packaged['endnote']['writeback_status'], 'not_attempted')


class ManualDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pdf = self.root / 'input.pdf'
        self.pdf.write_bytes(b'PDF identity fixture')
        self.manifest_path = self.root / 'paper-fixture.match.json'
        self.manifest = {
            'schema_version': '2.0', 'paper_id': 'sha256:' + bundle.digest(self.pdf),
            'source_pdf': {'path': str(self.pdf), 'filename': 'input.pdf', 'sha256': bundle.digest(self.pdf)},
            'bibliography': {'title': 'Article title', 'doi': '10.1000/primary', 'doi_status': 'verified',
                             'authors': [], 'year': '2026'},
            'extraction': {'status': 'text_extracted'},
            'endnote': {'library_path': '', 'record_number': None, 'status': 'not_checked',
                        'writeback_status': 'not_attempted'},
            'outputs': {'summary_markdown': '', 'research_notes': ''}}
        self.body = self.root / 'body.md'
        self.body.write_text('# Article title\nDOI: 10.1000/primary\nEvidence: PDF p. 1.\n', encoding='utf-8')

    def run_package(self, overwrite=False):
        bundle.write_json(self.manifest_path, self.manifest)
        with redirect_stdout(io.StringIO()):
            bundle.package(Namespace(manifest=self.manifest_path, body=self.body, notes=None, overwrite=overwrite))
        return json.loads(self.manifest_path.read_text(encoding='utf-8'))

    def test_title_doi_filename_and_original_metadata(self):
        result = self.run_package()
        path = Path(result['outputs']['summary_markdown'])
        self.assertEqual(path.name, 'Article title__10.1000_primary.md')
        self.assertIn('doi: "10.1000/primary"', path.read_text(encoding='utf-8'))
        self.assertEqual(result['delivery_mode'], 'manual_attachment')
        self.assertEqual(result['endnote']['writeback_status'], 'not_attempted')

    def test_forbidden_characters_and_device_names(self):
        self.assertEqual(bundle.filename_component('A/B\\C:D*E?F"G<H>I|J. '), 'A_B_C_D_E_F_G_H_I_J')
        for name in ('CON', 'PRN.txt', 'LPT1', 'COM¹.txt', 'AUX', 'NUL'):
            self.assertTrue(bundle.filename_component(name).startswith('_'))
        self.manifest['bibliography']['title'] = '../错误:标题/正文\x00'
        path = bundle.summary_path(self.manifest, self.root)
        self.assertEqual(path.parent, self.root)
        self.assertNotRegex(path.name, r'[<>:"/\\|?*\x00-\x1f]')

    def test_missing_and_unresolved_doi_never_invent_one(self):
        self.manifest['bibliography'].update(doi='', doi_status='missing')
        self.assertEqual(bundle.summary_path(self.manifest, self.root).name, 'Article title__无DOI.md')
        self.manifest['bibliography']['doi_status'] = 'unresolved'
        self.assertEqual(bundle.summary_path(self.manifest, self.root).name, 'Article title__DOI待核验.md')

    def test_unverified_doi_is_labeled_in_filename(self):
        self.manifest['bibliography']['doi_status'] = 'candidate'
        self.assertEqual(bundle.summary_path(self.manifest, self.root).name,
                         'Article title__10.1000_primary__DOI待核验.md')

    def test_unknown_title_uses_pdf_stem_without_faking_metadata(self):
        self.manifest['bibliography']['title'] = ''
        result = self.run_package()
        self.assertEqual(Path(result['outputs']['summary_markdown']).name, 'input__10.1000_primary.md')
        self.assertIn('title: ""', Path(result['outputs']['summary_markdown']).read_text(encoding='utf-8'))

    def test_long_unicode_title_retains_complete_doi(self):
        self.manifest['bibliography']['title'] = '超长🧪标题' * 100
        path = bundle.summary_path(self.manifest, self.root)
        self.assertLessEqual(bundle.utf16_length(str(path)), 240)
        self.assertLessEqual(bundle.utf16_length(path.name), 220)
        self.assertTrue(path.name.endswith('__10.1000_primary.md'))
        path.write_text('valid Unicode file', encoding='utf-8')
        self.assertTrue(path.is_file())

    def test_extreme_doi_length_keeps_full_value_in_metadata(self):
        self.manifest['bibliography']['doi'] = '10.1000/' + 'abc' * 150
        result = self.run_package()
        path = Path(result['outputs']['summary_markdown'])
        self.assertLessEqual(bundle.utf16_length(str(path)), 240)
        self.assertIn(self.manifest['bibliography']['doi'], path.read_text(encoding='utf-8'))

    def test_different_source_same_title_doi_cannot_overwrite(self):
        first = self.run_package()
        first_path = Path(first['outputs']['summary_markdown'])
        first_bytes = first_path.read_bytes()
        self.pdf.write_bytes(b'Different edition of source PDF')
        self.manifest['source_pdf']['sha256'] = bundle.digest(self.pdf)
        self.manifest['paper_id'] = 'sha256:' + bundle.digest(self.pdf)
        second = self.run_package(overwrite=True)
        second_path = Path(second['outputs']['summary_markdown'])
        self.assertNotEqual(first_path, second_path)
        self.assertIn(bundle.digest(self.pdf)[:8], second_path.name)
        self.assertEqual(first_path.read_bytes(), first_bytes)

    def test_unrelated_file_protected_even_with_overwrite(self):
        path = bundle.summary_path(self.manifest, self.root)
        path.write_text('User existing notes without paper identity', encoding='utf-8')
        result = self.run_package(overwrite=True)
        self.assertNotEqual(Path(result['outputs']['summary_markdown']), path)
        self.assertEqual(path.read_text(encoding='utf-8'), 'User existing notes without paper identity')

    def test_same_source_requires_explicit_regeneration(self):
        first = self.run_package()
        with self.assertRaises(ValueError):
            self.run_package()
        second = self.run_package(overwrite=True)
        self.assertEqual(first['outputs']['summary_markdown'], second['outputs']['summary_markdown'])

    def test_old_attachment_success_is_not_inherited(self):
        self.manifest['endnote'].update(writeback_status='attached', verification={'old': True},
                                       writeback_plan={'action': 'skip_existing'})
        result = self.run_package()
        self.assertEqual(result['previous_deliveries'][0]['endnote']['writeback_status'], 'attached')
        self.assertEqual(result['endnote']['writeback_status'], 'not_attempted')
        self.assertNotIn('verification', result['endnote'])
        self.assertNotIn('writeback_plan', result['endnote'])
        self.assertIn('writeback_status: "not_attempted"',
                      Path(result['outputs']['summary_markdown']).read_text(encoding='utf-8'))

    def test_changed_source_rejected_before_delivery(self):
        self.pdf.write_bytes(b'Changed after preparation')
        with self.assertRaises(ValueError):
            self.run_package()
        self.assertFalse(list(self.root.glob('Article title*.md')))

    def test_title_doi_folder_delivery_keeps_summary_and_manifest_together(self):
        folder = bundle.create_paper_folder(self.root, self.manifest['bibliography'], 'input')
        self.manifest_path = folder / self.manifest_path.name
        self.manifest['storage'] = {'layout': 'title_doi_folder', 'paper_directory': str(folder)}
        result = self.run_package()
        summary = Path(result['outputs']['summary_markdown'])
        self.assertEqual(folder.name, 'Article title__10.1000_primary')
        self.assertEqual(summary, folder / 'Article title__10.1000_primary.md')
        self.assertEqual(result['outputs']['summary_sha256'], bundle.digest(summary))
        line = next(line for line in summary.read_text(encoding='utf-8').splitlines()
                    if line.startswith('match_manifest: '))
        self.assertEqual(Path(json.loads(line.partition(': ')[2])), self.manifest_path)

    def test_repeated_folder_creation_preserves_old_results(self):
        first = bundle.create_paper_folder(self.root, self.manifest['bibliography'], 'input')
        existing = first / 'Article title__10.1000_primary.md'
        existing.write_text('Earlier user notes', encoding='utf-8')
        second = bundle.create_paper_folder(self.root, self.manifest['bibliography'], 'input')
        self.assertEqual(second.name, first.name + '__2')
        self.assertEqual(existing.read_text(encoding='utf-8'), 'Earlier user notes')
        self.assertEqual(list(second.iterdir()), [])

    def test_folder_label_cannot_escape_storage_and_marks_unverified_doi(self):
        self.manifest['bibliography'].update(title='../错误:标题/正文', doi_status='candidate')
        folder = bundle.create_paper_folder(self.root, self.manifest['bibliography'], 'input')
        self.assertEqual(folder.parent, self.root)
        self.assertNotRegex(folder.name, r'[<>:"/\\|?*\x00-\x1f]')
        self.assertTrue(folder.name.endswith('__10.1000_primary__DOI待核验'))

    def test_folder_summary_name_still_protects_unrelated_notes(self):
        folder = bundle.create_paper_folder(self.root, self.manifest['bibliography'], 'input')
        existing = folder / 'Article title__10.1000_primary.md'
        existing.write_text('Existing user notes', encoding='utf-8')
        self.manifest['storage'] = {'layout': 'title_doi_folder'}
        self.manifest_path = folder / self.manifest_path.name
        result = self.run_package(overwrite=True)
        self.assertNotEqual(Path(result['outputs']['summary_markdown']), existing)
        self.assertEqual(existing.read_text(encoding='utf-8'), 'Existing user notes')

    def test_long_folder_label_leaves_room_for_evidence_paths(self):
        self.manifest['bibliography']['title'] = '超长🧪标题' * 100
        folder = bundle.create_paper_folder(self.root, self.manifest['bibliography'], 'input')
        evidence = folder / 'paper-1234567890abcdef.match.json'
        self.assertLessEqual(bundle.utf16_length(str(evidence)), 240)
        self.assertTrue(folder.name.endswith('__10.1000_primary'))
        evidence.write_text('{}', encoding='utf-8')
        self.assertTrue(evidence.is_file())

    def test_long_folder_reserves_room_for_title_doi_markdown(self):
        title = 'Mid-gap trap state-mediated dark current in organic photodiodes'
        self.manifest['bibliography'].update(title=title, doi='10.1038/s41566-023-01173-5')
        root = self.root / ('r' * 25)
        folder = bundle.create_paper_folder(root, self.manifest['bibliography'], 'input')
        self.manifest['storage'] = {'layout': 'title_doi_folder'}
        summary = bundle.summary_path(self.manifest, folder)
        self.assertEqual(summary.name, title + '__10.1038_s41566-023-01173-5.md')
        self.assertLessEqual(bundle.utf16_length(str(summary)), 240)
        summary.write_text('Summary content', encoding='utf-8')
        self.assertTrue(summary.is_file())

    def test_prepare_flag_returns_all_evidence_in_fresh_folder(self):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        with self.pdf.open('wb') as stream:
            writer.write(stream)
        bib = self.root / 'bibliography.json'
        bib.write_text(json.dumps({'title':'Article title', 'doi':'10.1000/primary',
                                  'doi_status':'verified', 'doi_evidence':['fixture']}), encoding='utf-8')
        args = Namespace(pdf=self.pdf, output_dir=self.root, bibliography=bib,
                         library=None, endnote_xml=None, overwrite=False, paper_folder=True)
        replies = []
        for _ in range(2):
            output = io.StringIO()
            with redirect_stdout(output):
                bundle.prepare(args)
            replies.append(json.loads(output.getvalue()))
        first, second = (Path(reply['manifest']) for reply in replies)
        self.assertNotEqual(first.parent, second.parent)
        self.assertEqual(second.parent.name, first.parent.name + '__2')
        for reply in replies:
            manifest_path = Path(reply['manifest'])
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            self.assertEqual(Path(reply['source']).parent, manifest_path.parent)
            self.assertEqual(manifest['storage']['paper_directory'], str(manifest_path.parent))
            self.assertEqual(manifest['endnote']['writeback_status'], 'not_attempted')


class WritebackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = self.root / 'library.enl'
        self.library.write_bytes(b'fixture library identity only')
        self.copies = self.library.with_suffix('.Data') / 'PDF' / '123'
        self.copies.mkdir(parents=True)
        self.pdf = self.copies / 'source.pdf'
        self.pdf.write_bytes(b'PDF fixture')
        self.summary = self.root / 'paper.summary.md'
        self.summary.write_text('# Summary\nEvidence and limitations\n', encoding='utf-8')
        self.copy = self.copies / self.summary.name
        self.manifest = self.root / 'paper.match.json'
        bundle.write_json(self.manifest, {'bibliography': {'doi': '10.1000/primary', 'doi_status': 'verified', 'title': 'Primary work'},
            'source_pdf': {'path': str(self.pdf), 'sha256': bundle.digest(self.pdf)}, 'summary_status': 'ready',
            'outputs': {'summary_markdown': str(self.summary), 'summary_sha256': bundle.digest(self.summary)}})
        self.before = self.root / 'before.xml'
        self.after = self.root / 'after.xml'
        self.export(self.before)
        self.obs = self.root / 'native.json'
        bundle.write_json(self.obs, {'library_path': str(self.library), 'record_number': '1', 'title': 'Primary work',
            'doi': '10.1000/primary', 'reference_reopened': True, 'observed_at': '2026-10-06T00:00:00Z',
            'attachments': [{'displayed_filename': self.pdf.name, 'path': str(self.pdf)},
                            {'displayed_filename': self.copy.name, 'path': str(self.copy)}]})

    def export(self, path, md=False, pdf=True, extra=False, note='User notes', duplicate=False):
        attachments = (['internal-pdf://123/source.pdf'] if pdf else []) + (['internal-pdf://123/paper.summary.md'] if md else [])
        def record(number, links):
            urls = ''.join('<url>'+escape(u)+'</url>' for u in links)
            return f'<record><database path="{escape(str(self.library), quote=True)}"/><rec-number>{number}</rec-number><titles><title>Primary work</title></titles><electronic-resource-num>10.1000/primary</electronic-resource-num><notes>{escape(note)}</notes><urls><pdf-urls>{urls}</pdf-urls></urls></record>'
        content = record('1', attachments)
        if extra:
            content += record('2', [])
        if duplicate:
            content += record('1', attachments)
        path.write_text('<xml><records>'+content+'</records></xml>', encoding='utf-8')

    def plan(self, xml=None, observation=None):
        writeback.plan(Namespace(manifest=self.manifest, library=self.library, xml=xml or self.before, native_observation=observation))

    def verify(self, observation=None):
        writeback.verify(Namespace(manifest=self.manifest, xml=self.after, native_observation=observation,
                                  opened_attachment=self.copy, opened_app='ObservedApp'))

    def test_registered_xml_attachment_verified(self):
        self.plan()
        self.copy.write_bytes(self.summary.read_bytes())
        self.export(self.after, md=True)
        self.verify()
        result = json.loads(self.manifest.read_text(encoding='utf-8'))
        self.assertEqual(result['endnote']['writeback_status'], 'attached')
        self.assertTrue(result['endnote']['verification']['opened_in_app'])

    def test_disk_copy_without_registered_observation_is_insufficient(self):
        self.plan()
        self.copy.write_bytes(self.summary.read_bytes())
        self.export(self.after)
        with self.assertRaises(ValueError):
            self.verify()

    def test_xml_omitted_markdown_verified_by_native_observation(self):
        self.plan()
        self.copy.write_bytes(self.summary.read_bytes())
        self.export(self.after)
        self.verify(self.obs)
        self.assertEqual(json.loads(self.manifest.read_text())['endnote']['writeback_status'], 'attached')

    def test_repeat_skips_identical_native_attachment(self):
        self.copy.write_bytes(self.summary.read_bytes())
        self.plan(observation=self.obs)
        self.assertEqual(json.loads(self.manifest.read_text())['endnote']['writeback_plan']['action'], 'skip_existing')
        self.export(self.after)
        self.verify(self.obs)

    def test_wrong_native_record_rejected(self):
        self.copy.write_bytes(self.summary.read_bytes())
        value = json.loads(self.obs.read_text())
        value['record_number'] = '2'
        bundle.write_json(self.obs, value)
        with self.assertRaises(ValueError):
            self.plan(observation=self.obs)

    def test_added_reference_rejected(self):
        self.plan()
        self.copy.write_bytes(self.summary.read_bytes())
        self.export(self.after, md=True, extra=True)
        with self.assertRaises(ValueError):
            self.verify()

    def test_removed_original_pdf_rejected(self):
        self.plan()
        self.copy.write_bytes(self.summary.read_bytes())
        self.export(self.after, md=True, pdf=False)
        with self.assertRaises(ValueError):
            self.verify()

    def test_user_notes_change_rejected(self):
        self.plan()
        self.copy.write_bytes(self.summary.read_bytes())
        self.export(self.after, md=True, note='Changed user notes')
        with self.assertRaises(ValueError):
            self.verify()

    def test_wrong_attachment_content_rejected(self):
        self.plan()
        self.copy.write_text('Wrong summary')
        self.export(self.after, md=True)
        with self.assertRaises(ValueError):
            self.verify()

    def test_changed_summary_rejected_before_plan(self):
        self.summary.write_text('Changed unpackaged summary')
        with self.assertRaises(ValueError):
            self.plan()

    def test_wrong_library_export_rejected(self):
        xml = self.before.read_text(encoding='utf-8').replace(escape(str(self.library), quote=True), 'different.enl')
        self.before.write_text(xml, encoding='utf-8')
        with self.assertRaises(ValueError):
            self.plan()

    def test_duplicate_record_ids_rejected(self):
        self.export(self.before, duplicate=True)
        with self.assertRaises(ValueError):
            self.plan()


if __name__ == '__main__':
    unittest.main()
