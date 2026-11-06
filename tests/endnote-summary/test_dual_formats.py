from pathlib import Path
import base64,importlib.util,json,subprocess,tempfile,unittest,sys,types
from argparse import Namespace
from unittest.mock import patch,MagicMock

HERE=Path(__file__).resolve().parent
SKILL=HERE.parents[1]/'skills'/'endnote-summary'
spec=importlib.util.spec_from_file_location('sync',SKILL/'scripts'/'zotero_sync.py')
sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)
PARENT={'key':'PARENT','data':{'title':'Primary work','DOI':'10.1000/primary','itemType':'journalArticle'}}
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')

class DualFormatTests(unittest.TestCase):
 def setUp(self):
  (HERE/'tmp').mkdir(exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=HERE/'tmp');self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);(self.root/'figures').mkdir()
  self.image=self.root/'figures'/'f.png';self.image.write_bytes(PNG)
  self.md=self.root/'summary.md';self.md.write_text('# Primary work\n\n![original](figures/f.png)\n',encoding='utf-8')
  self.manifest=self.root/'paper.match.json'
  sync.write_json(self.manifest,{'summary_status':'ready','outputs':{'summary_markdown':str(self.md),'summary_sha256':sync.digest(self.md)},'bibliography':{'title':'Primary work','doi':'10.1000/primary','doi_status':'verified'},'source_pdf':{'sha256':'unused'}})
  with patch.object(sync,'candidates',return_value=PARENT),patch.object(sync,'get',return_value=[]):
   sync.prepare(Namespace(manifest=self.manifest,legacy_script=True))
  self.plan=self.root/'zotero-sync-plan.json';self.html=self.md.with_suffix('.html')
  self.saved=self.root/'storage';self.saved.mkdir()
  self.htmlcopy=self.saved/'summary.html';self.htmlcopy.write_bytes(self.html.read_bytes())
  self.mdcopy=self.saved/'summary.md';self.mdcopy.write_bytes(self.md.read_bytes())
  (self.saved/'figures').mkdir();(self.saved/'figures'/'f.png').write_bytes(PNG)
  self.htmlitem=self.item('HTML',self.htmlcopy,'text/html');self.mditem=self.item('MD',self.mdcopy,'text/markdown')
 def item(self,key,path,ctype):
  return {'key':key,'data':{'contentType':ctype,'parentItem':'PARENT','linkMode':'imported_file'},'links':{'enclosure':{'href':path.as_uri()}}}
 def verify(self,rows):
  with patch.object(sync,'get',return_value=rows):return sync.verify(Namespace(plan=self.plan))
 def test_prepare_requires_both_formats(self):
  plan=sync.read_json(self.plan)
  self.assertEqual(plan['required_formats'],['html','markdown'])
  self.assertEqual(plan['images'][0]['sha256'],sync.digest(self.image))
 def test_both_imports_and_images_verified(self):
  receipt=self.verify([self.htmlitem,self.mditem]);self.assertEqual(set(receipt['attachments']),{'html','markdown'})
  self.assertEqual(receipt['attachments']['markdown']['images_verified'],1)
  self.assertEqual(receipt['cloud_sync_status'],'not_verified')
 def test_html_alone_cannot_claim_dual_delivery(self):
  with self.assertRaisesRegex(ValueError,'Markdown'):self.verify([self.htmlitem])
  self.assertFalse((self.root/'zotero-sync-receipt.json').exists())
 def test_missing_md_image_fails(self):
  (self.saved/'figures'/'f.png').unlink()
  with self.assertRaisesRegex(ValueError,'image'):self.verify([self.htmlitem,self.mditem])
 def test_corrupt_md_image_fails(self):
  (self.saved/'figures'/'f.png').write_bytes(b'broken')
  with self.assertRaisesRegex(ValueError,'image'):self.verify([self.htmlitem,self.mditem])
 def test_linked_md_cannot_pass(self):
  self.mditem['data']['linkMode']='linked_file'
  with self.assertRaisesRegex(ValueError,'imported'):self.verify([self.htmlitem,self.mditem])
 def test_wrong_parent_md_cannot_pass(self):
  self.mditem['data']['parentItem']='OTHER'
  with self.assertRaisesRegex(ValueError,'parent'):self.verify([self.htmlitem,self.mditem])
 def test_native_import_copy_dedup_and_partial_repair(self):
  subprocess.run(['node',str(HERE/'test_native.mjs'),str(self.root)],check=True,capture_output=True,text=True)
 def test_default_official_api_saves_both_and_copies_images(self):
  (self.saved/'figures'/'f.png').unlink()
  client=MagicMock()
  client.attach_file.side_effect=[{'status':'already_present','attachment_path':str(self.htmlcopy),'attachment_key':'HTML'},{'status':'saved','attachment_path':str(self.mdcopy),'attachment_key':'MD'}]
  with patch.dict(sys.modules,{'zotero_local_api':types.SimpleNamespace(Client=lambda:client)}),patch.object(sync,'get',return_value=[self.htmlitem,self.mditem]):
   receipt=sync.save(Namespace(manifest=None,plan=self.plan))
  self.assertEqual(client.attach_file.call_count,2)
  self.assertEqual(client.attach_file.call_args_list[1].kwargs['path'],str(self.md))
  self.assertEqual((self.saved/'figures'/'f.png').read_bytes(),PNG)
  self.assertEqual(receipt['transport'],'official_local_api')
  self.assertEqual(receipt['save_status'],{'html':'already_present','markdown':'saved'})
 def test_prepare_default_does_not_generate_legacy_script(self):
  (self.root/'zotero-attach.js').unlink()
  with patch.object(sync,'candidates',return_value=PARENT),patch.object(sync,'get',return_value=[]):
   result=sync.prepare(Namespace(manifest=self.manifest))
  self.assertIsNone(result['native_script'])
  self.assertFalse((self.root/'zotero-attach.js').exists())

class ProbeTests(unittest.TestCase):
 def setUp(self):
  (HERE/'tmp').mkdir(exist_ok=True);self.temp=tempfile.TemporaryDirectory(dir=HERE/'tmp');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
 def probe(self,path):
  item={'key':'PDF','data':{'contentType':'application/pdf','title':'Primary work'},'links':{'enclosure':{'href':path.as_uri()}}}
  with patch.object(sync,'candidates',return_value=PARENT),patch.object(sync,'get',return_value=[item]):return sync.probe(Namespace(title='Primary work',doi='10.1000/primary',out=None))
 def test_missing_record_is_not_usable_pdf(self):
  result=self.probe(self.root/'absent.pdf');self.assertEqual(result['files'][0]['status'],'missing');self.assertEqual(result['usable_pdf_keys'],[])
 def test_html_disguised_as_pdf_rejected(self):
  p=self.root/'login.pdf';p.write_text('<html>Login</html>');self.assertEqual(self.probe(p)['files'][0]['status'],'unreadable')
 def test_local_pdf_is_usable_without_download(self):
  from pypdf import PdfWriter
  p=self.root/'actual.pdf';w=PdfWriter();w.add_blank_page(width=200,height=200)
  with p.open('wb') as f:w.write(f)
  r=self.probe(p);self.assertEqual(r['usable_pdf_keys'],['PDF']);self.assertEqual(r['files'][0]['sha256'],sync.digest(p));self.assertEqual(r['files'][0]['text_status'],'ocr_or_visual_reading_required')
 def test_remote_image_not_fetched(self):
  p=self.root/'summary.md';p.write_text('![x](https://example.org/secret.png)',encoding='utf-8')
  with self.assertRaises(ValueError):sync.make_html(p,'Test')

if __name__=='__main__':unittest.main(verbosity=2)
