"""Observable crop fidelity, source binding, and movable Markdown package tests."""
from pathlib import Path
import importlib.util
import json
import math
import shutil
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[2] / 'skills' / 'endnote-summary'
spec = importlib.util.spec_from_file_location('figure_assets', SKILL_ROOT / 'scripts/figure_assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class FigureAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paper = self.root / 'paper'
        self.paper.mkdir()
        self.pdf = self.paper / 'article.pdf'
        self.make_pdf()
        self.plan = self.paper / 'figure-plan.json'
        self.data = {'sources': {'main': {'path': 'article.pdf', 'sha256': assets.sha256(self.pdf)}},
            'items': [{'id':'main_fig01','source':'main','kind':'figure','number':'1',
                       'page':1,'selected':True,'bbox':[0,0,0.5,1],'panels':['a','b']} ]}

    def make_pdf(self, rotated=False):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, NameObject
        writer = PdfWriter()
        page = writer.add_blank_page(200,100)
        content = DecodedStreamObject()
        content.set_data(b'q 1 0 0 rg 0 0 100 100 re f 0 0 1 rg 100 0 100 100 re f Q')
        page[NameObject('/Contents')] = writer._add_object(content)
        if rotated:
            page.rotate(90)
        with self.pdf.open('wb') as stream:
            writer.write(stream)

    def render(self):
        self.plan.write_text(json.dumps(self.data),encoding='utf-8')
        return assets.render(self.plan,self.paper,dpi=144)

    def markdown(self, link='figures/main_fig01.png'):
        path = self.paper / 'summary.md'
        path.write_text(f'# Summary\n![Source figure]({link})\n',encoding='utf-8')
        return path

    def test_crop_uses_rendered_vectors_and_normalized_region(self):
        from PIL import Image
        manifest = self.render()
        with Image.open(self.paper/'figures/main_fig01.png') as image:
            self.assertEqual(image.size,(200,200))
            self.assertEqual(image.getpixel((100,100))[:3],(255,0,0))
        report = assets.check(manifest,self.markdown())
        self.assertTrue(report['structure_ok'])
        self.assertEqual(report['reader_reviews_pending'],['main_fig01'])

    def test_rotated_page_boxes_follow_display_orientation(self):
        from PIL import Image
        self.make_pdf(rotated=True)
        self.data['sources']['main']['sha256']=assets.sha256(self.pdf)
        self.data['items'][0]['bbox']=[0,0,1,0.5]
        self.render()
        with Image.open(self.paper/'figures/main_fig01.png') as image:
            self.assertEqual(image.size,(200,200))
            self.assertEqual(image.getpixel((100,100))[:3],(255,0,0))

    def test_wrong_source_hash_fails_before_artifacts(self):
        self.data['sources']['main']['sha256']='0'*64
        with self.assertRaises(ValueError): self.render()
        self.assertFalse((self.paper/'figures').exists())

    def test_page_outside_source_fails_before_crop(self):
        self.data['items'][0]['page']=2
        with self.assertRaises(ValueError): self.render()
        self.assertFalse((self.paper/'figures').exists())

    def test_invalid_empty_or_nan_boxes_rejected(self):
        for box in [[0,0,1.1,1],[0.5,0,0.4,1],[0,0,1,float('nan')],[False,0,1,1]]:
            self.data['items'][0]['bbox']=box
            with self.subTest(box=box), self.assertRaises(ValueError): self.render()

    def test_main_cannot_be_omitted(self):
        self.data['items'][0]['selected']=False
        with self.assertRaises(ValueError): self.render()

    def test_si_requires_reason_and_reports_omissions(self):
        self.data['sources']['si1']=dict(self.data['sources']['main'])
        self.data['items'].append({'id':'si1_figS01','source':'si1','kind':'figure',
            'number':'S1','page':1,'selected':False})
        with self.assertRaises(ValueError): self.render()
        self.data['items'][1]['selection_reason']='Read; duplicative intermediate spectrum, no separate discussion.'
        manifest=self.render()
        report=assets.check(manifest,self.markdown())
        self.assertTrue(report['structure_ok'])
        self.assertEqual(report['omitted_si'][0]['id'],'si1_figS01')

    def test_duplicates_and_path_ids_rejected(self):
        self.data['items'].append(dict(self.data['items'][0]))
        with self.assertRaises(ValueError): self.render()
        self.data['items']=self.data['items'][:1]
        self.data['items'][0]['id']='../outside'
        with self.assertRaises(ValueError): self.render()

    def test_selected_image_must_appear_in_final_markdown(self):
        manifest=self.render()
        md=self.markdown()
        md.write_text('# Text only',encoding='utf-8')
        self.assertFalse(assets.check(manifest,md)['structure_ok'])

    def test_changed_crop_or_source_is_reported(self):
        manifest=self.render()
        md=self.markdown()
        crop=self.paper/'figures/main_fig01.png'
        original=crop.read_bytes()
        crop.write_bytes(b'not a PNG')
        self.assertFalse(assets.check(manifest,md)['structure_ok'])
        crop.write_bytes(original)
        self.pdf.write_bytes(self.pdf.read_bytes()+b'\n% modified')
        self.assertFalse(assets.check(manifest,md)['structure_ok'])

    def test_external_or_escape_image_links_rejected(self):
        manifest=self.render()
        for link in ['../outside.png','https://example.com/image.png','C:/outside.png']:
            with self.subTest(link=link):
                self.assertFalse(assets.check(manifest,self.markdown(link))['structure_ok'])

    def test_existing_crop_not_overwritten_implicitly(self):
        self.render()
        original=(self.paper/'figures/main_fig01.png').read_bytes()
        with self.assertRaises(ValueError): self.render()
        self.assertEqual((self.paper/'figures/main_fig01.png').read_bytes(),original)

    def test_whole_paper_folder_can_move_with_links_and_source_binding(self):
        self.render()
        self.markdown()
        moved=self.root/'moved'
        shutil.copytree(self.paper,moved)
        shutil.rmtree(self.paper)
        self.assertTrue(assets.check(moved/'figure-assets.json',moved/'summary.md')['structure_ok'])


if __name__=='__main__':
    unittest.main()
