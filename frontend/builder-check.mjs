import {JSDOM,VirtualConsole} from 'jsdom';
import {build} from 'esbuild';
import assert from 'node:assert/strict';
const result=await build({entryPoints:['src/main.jsx'],bundle:true,write:false,outfile:'out.js',format:'iife',loader:{'.css':'empty','.txt':'text'},define:{'process.env.NODE_ENV':'"development"'}});
const errors=[],drafts=[];let pdfRequest=null,downloaded=false;
const vc=new VirtualConsole();vc.on('error',(...args)=>errors.push(args.join(' ')));vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
 w.confirm=()=>true;
 w.URL.createObjectURL=()=> 'blob:test';w.URL.revokeObjectURL=()=>{};
 w.HTMLAnchorElement.prototype.click=function(){downloaded=this.download==='Alex Morgan.pdf'};
 w.ResizeObserver=class{constructor(callback){this.callback=callback}observe(target){this.callback([{target,contentRect:{width:1000,height:340}}])}unobserve(){}disconnect(){}};
 w.HTMLElement.prototype.getBoundingClientRect=function(){return {width:this.classList.contains('document-canvas')?1000:600,height:340}};
 w.fetch=async(url,options={})=>{
  if(url==='/api/applications')return {ok:true,json:async()=>[]};
  if(url==='/api/resume-drafts/pdf'){pdfRequest=JSON.parse(options.body);return {ok:true,blob:async()=>new w.Blob(['%PDF-1.4'],{type:'application/pdf'})}};
  if(url.startsWith('/api/resume-drafts')){
   if(!options.method)return {ok:true,json:async()=>drafts};
   const saved={...JSON.parse(options.body),id:'a'.repeat(32),updated_at:new Date().toISOString()};drafts.splice(0,drafts.length,saved);return {ok:true,json:async()=>saved};
  }
  throw Error('Unexpected URL '+url);
 };
}});
dom.window.eval(result.outputFiles[0].text);
const wait=()=>new Promise(r=>setTimeout(r,40));await wait();
const doc=dom.window.document;
function button(text){const b=[...doc.querySelectorAll('button')].find(b=>b.textContent===text);assert.ok(b,text);return b}
function edit(label,value){const el=doc.querySelector(`[role="textbox"][aria-label="${label}"]`);assert.ok(el,label);el.textContent=value;el.dispatchEvent(new dom.window.Event('input',{bubbles:true}));}
function select(label,value){const el=doc.querySelector(`select[aria-label="${label}"]`);assert.ok(el,label);el.value=value;el.dispatchEvent(new dom.window.Event('change',{bubbles:true}));}
button('Resume Builder').click();await wait();
assert.ok(doc.querySelector('.document-builder'));
assert.ok(Number(doc.querySelector('.resume-paper').style.zoom)>1,'Fit width should fill a large canvas');
edit('Full name','Alex Morgan');await wait();
edit('Professional summary','Build reliable data products.');await wait();
button('Add experience').click();await wait();
edit('Job title','Data Scientist');await wait();
edit('Company','Example');await wait();
edit('Dates','2024 – Present');await wait();
edit('Experience 1 bullet 1','Built a data pipeline.');await wait();
const bullet=doc.querySelector('[aria-label="Experience 1 bullet 1"]');bullet.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await wait();
edit('Experience 1 bullet 2','Improved model quality.');await wait();
doc.querySelector('[aria-label="Move bullet 2 up in experience 1"]').click();await wait();
assert.equal(doc.querySelector('[aria-label="Experience 1 bullet 1"]').textContent,'Improved model quality.');
doc.querySelector('[aria-label="Remove bullet 2 from experience 1"]').click();await wait();
assert.equal(doc.querySelectorAll('[aria-label^="Experience 1 bullet"]').length,1);
// Add and reorder a section, preserving its text through undo/redo.
select('Section to add','certifications');await wait();doc.querySelector('[aria-label="Add section"]').click();await wait();
edit('Certifications','AWS Certified');await wait();
doc.querySelector('[aria-label="Move Certifications up"]').click();await wait();
let order=[...doc.querySelectorAll('.inline-section')].map(s=>s.dataset.section);
assert.ok(order.indexOf('certifications')<order.indexOf('skills'));
doc.querySelector('[aria-label="Undo"]').click();await wait();
order=[...doc.querySelectorAll('.inline-section')].map(s=>s.dataset.section);
assert.ok(order.indexOf('certifications')>order.indexOf('skills'));
doc.querySelector('[aria-label="Redo"]').click();await wait();
button('Save resume').click();await wait();
assert.equal(drafts[0].name,'Alex Morgan');assert.equal(drafts[0].experience[0].title,'Data Scientist');
assert.equal(drafts[0].experience[0].description,'Improved model quality.');
assert.equal(drafts[0].certifications,'AWS Certified');assert.equal(drafts[0].font_family,'Times New Roman');
edit('Professional summary','Unsaved PDF edits included.');await wait();
button('Download PDF').click();await wait();
assert.equal(pdfRequest.summary,'Unsaved PDF edits included.');assert.ok(downloaded);
assert.equal(pdfRequest.paper_size,'Legal');assert.ok(pdfRequest.section_order.includes('certifications'));
doc.querySelector('[aria-label="Preview PDF"]').click();await wait();
assert.ok(doc.querySelector('[title="Generated PDF preview"]'));
doc.querySelector('[aria-label="Back to editor"]').click();await wait();
assert.ok(doc.querySelector('.inline-resume'));
button('Overview').click();await wait();button('Resume Builder').click();await wait();
assert.ok(doc.querySelector('.resume-paper').textContent.includes('Unsaved PDF edits included.'));
button('New resume').click();await wait();
assert.equal(doc.querySelector('[aria-label="Full name"]').textContent,'');
select('Saved resumes','a'.repeat(32));await wait();
assert.ok(doc.querySelector('.resume-paper').textContent.includes('Build reliable data products.'));
assert.equal(errors.length,0,errors.join('\n'));
console.log('Inline editor: text/bullet editing, Enter, bullet reorder/remove, sections, undo/redo, save/reopen, PDF export/proof, and navigation passed.');
dom.window.close();
