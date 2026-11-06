import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=process.argv[2];
const plan=JSON.parse(await fs.readFile(path.join(root,'zotero-sync-plan.json'),'utf8'));
const code=await fs.readFile(path.join(root,'zotero-attach.js'),'utf8');
const initialHtml=path.join(root,'mock-library','OLDHTML','summary.html');
await fs.mkdir(path.dirname(initialHtml),{recursive:true});await fs.copyFile(plan.html_path,initialHtml);
const items=new Map();let created=0;
function item(key,file,type){return {key,attachmentContentType:type,attachmentLinkMode:0,getFilePathAsync:async()=>file};}
items.set('OLDHTML',item('OLDHTML',initialHtml,'text/html'));
const parent={id:1,key:'PARENT',deleted:false,isRegularItem:()=>true,getField:k=>k==='title'?'Primary work':'10.1000/primary',getAttachments:()=>[...items.keys()]};
const Zotero={Libraries:{userLibraryID:1},Items:{getByLibraryAndKeyAsync:async()=>parent,getAsync:async k=>items.get(k)},Attachments:{LINK_MODE_IMPORTED_FILE:0,importFromFile:async o=>{
 assert.equal(o.parentItemID,1);const key='NEW'+(++created);const file=path.join(root,'mock-library',key,path.basename(o.file));await fs.mkdir(path.dirname(file),{recursive:true});await fs.copyFile(o.file,file);const i=item(key,file,o.contentType);items.set(key,i);return i;
}},File:{copyFile:async(a,b)=>fs.copyFile(a,b),putContentsAsync:async(p,s)=>fs.writeFile(p,s)},getActiveZoteroPane:()=>({selectItem:async()=>{}})};
const IOUtils={read:async p=>fs.readFile(p),readUTF8:async p=>fs.readFile(p,'utf8'),exists:async p=>{try{await fs.access(p);return true;}catch{return false;}},makeDirectory:async p=>fs.mkdir(p,{recursive:true})};
const Components={classes:{'@mozilla.org/process/environment;1':{getService:()=>({get:()=>plan.machine_name})}},interfaces:{nsIEnvironment:{}}};
const run=()=>new (Object.getPrototypeOf(async()=>{}).constructor)('Zotero','IOUtils','OS','Components',code)(Zotero,IOUtils,{Path:path},Components);
const first=JSON.parse(await run());assert.equal(first.attachments.html.attachment_key,'OLDHTML');assert.equal(created,1);assert.equal(first.attachments.markdown.status,'saved');
const md=first.attachments.markdown.attachment_path;const img=path.join(path.dirname(md),'figures','f.png');assert.deepEqual(await fs.readFile(img),await fs.readFile(path.join(root,'figures','f.png')));
await run();assert.equal(created,1,'Retry must not create duplicates');
await fs.unlink(img);await run();assert.equal(created,1);assert.deepEqual(await fs.readFile(img),await fs.readFile(path.join(root,'figures','f.png')));
await fs.writeFile(img,'conflict');await assert.rejects(run(),/resource differs/);assert.equal(created,1,'Conflicting image must not cause another MD import');
console.log('Native import: old HTML reused; MD and resources added; retry deduplicated; missing image repaired; conflicting image rejected.');
