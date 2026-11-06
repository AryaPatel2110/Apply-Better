import {JSDOM, VirtualConsole} from 'jsdom';
import {build} from 'esbuild';
import assert from 'node:assert/strict';
const result=await build({entryPoints:['src/main.jsx'],bundle:true,write:false,outfile:'out.js',format:'iife',loader:{'.css':'empty','.txt':'text'},define:{'process.env.NODE_ENV':'"development"'}});
const rows=[{id:'test-application',company:'Example',job_title:'Engineer',job_description:'Build products.',job_link:'https://example.com/job',applied_date:'2026-10-01',status:'Interviewing',resume_name:'resume.pdf',status_history:[{status:'Applied',at:null},{status:'Online Assessment',at:null},{status:'Interviewing',at:null}]}];
for(const format of ['parsed','string','missing','invalid']) {
 const errors=[];
 const vc=new VirtualConsole();
 vc.on('error',(...args)=>errors.push(args.map(String).join(' ')));
 vc.on('jsdomError',error=>errors.push(error.message));
 let lastPatch=null;
 const data=rows.map(row=>({...row,status_history:format==='parsed'?row.status_history:format==='string'?JSON.stringify(row.status_history):format==='missing'?undefined:'invalid json'}));
 const dom=new JSDOM('<div id="root"></div>',{runScripts:'dangerously',pretendToBeVisual:true,url:'http://localhost/',virtualConsole:vc,beforeParse(w){
   w.fetch=async(url,options)=>{if(url==='/api/resume-drafts')return {ok:true,json:async()=>[]};if(options?.method==='PATCH'){lastPatch=JSON.parse(options.body);const row=data.find(row=>url.endsWith(row.id));return {ok:true,json:async()=>({...row,status:lastPatch.status,status_history:lastPatch.status_history.map(status=>({status,at:null}))})}}return {ok:true,json:async()=>data}};
   w.ResizeObserver=class{constructor(callback){this.callback=callback}observe(target){this.callback([{target,contentRect:{width:600,height:340}}])}unobserve(){}disconnect(){}};
   w.HTMLElement.prototype.getBoundingClientRect=function(){return {width:600,height:340,top:0,left:0,right:600,bottom:340}};
 }});
 dom.window.eval(result.outputFiles[0].text);
 await new Promise(resolve=>setTimeout(resolve,400));
 const document=dom.window.document;
 assert.equal(errors.length,0,errors.join('\n'));
 assert.ok(document.body.textContent.includes('Dashboard'));
 assert.equal(document.querySelectorAll('svg.recharts-surface').length,2);
 assert.ok(document.querySelector('.flow-diagram svg'));
 assert.ok(document.querySelector('.flow-node-value'));
 assert.equal(document.querySelectorAll('.flow-column-label').length,0);
 assert.equal(document.querySelectorAll('.flow-node-context').length,0);
 assert.equal(document.querySelectorAll('.flow-diagram rect[fill="#fff"]').length,0);
 assert.equal(document.querySelectorAll('tbody tr').length,Math.min(5,rows.length));
 document.querySelector('.company-cell')?.click();
 await new Promise(resolve=>setTimeout(resolve,50));
 assert.ok(document.querySelector('[role="dialog"]'));
 assert.ok(document.querySelector('.status-history li'));
 [...document.querySelectorAll('button')].find(button=>button.textContent==='Edit history').click();
 await new Promise(resolve=>setTimeout(resolve,30));
 [...document.querySelectorAll('button')].find(button=>button.textContent==='Save history').click();
 await new Promise(resolve=>setTimeout(resolve,80));
 assert.ok(Array.isArray(lastPatch.status_history));
 assert.equal(lastPatch.status,lastPatch.status_history.at(-1));
 assert.equal(document.querySelector('.history-editor'),null);

 assert.equal(errors.length,0,errors.join('\n'));
 dom.window.close();
 console.log(`${format} history: dashboard, three charts, application table, and details passed`);
}
