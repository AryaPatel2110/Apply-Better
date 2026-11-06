import {useLayoutEffect} from 'react';

export const PAGE_GAP=28;

// Page breaks decorate the DOM; they never become part of the saved resume text.
export function editableText(element){
 const copy=element.cloneNode(true);
 copy.querySelectorAll('[data-inline-page-break]').forEach(node=>node.remove());
 let text='';
 function read(node){
  if(node.nodeType===3){text+=node.nodeValue;return}
  if(node.nodeName==='BR'){text+='\n';return}
  const block=['DIV','P'].includes(node.nodeName);
  if(block&&text&&!text.endsWith('\n'))text+='\n';
  node.childNodes.forEach(read);
  if(block&&!text.endsWith('\n'))text+='\n';
 }
 copy.childNodes.forEach(read);
 if(copy.lastChild&&['DIV','P'].includes(copy.lastChild.nodeName))text=text.replace(/\n$/,'');
 return text.replace(/\r\n/g,'\n');
}

function textNodes(element){
 const walker=document.createTreeWalker(element,NodeFilter.SHOW_TEXT);
 const nodes=[];let node;
 while((node=walker.nextNode()))if(!node.parentElement.closest('[data-inline-page-break]'))nodes.push(node);
 return nodes;
}
function bookmark(root){
 const element=document.activeElement;
 if(!element?.matches('[contenteditable="true"]')||!root.contains(element))return null;
 const selection=window.getSelection();
 if(!selection?.rangeCount)return null;
 const selected=selection.getRangeAt(0);
 if(!element.contains(selected.startContainer)||!element.contains(selected.endContainer))return null;
 const start=document.createRange();start.selectNodeContents(element);start.setEnd(selected.startContainer,selected.startOffset);
 const end=document.createRange();end.selectNodeContents(element);end.setEnd(selected.endContainer,selected.endOffset);
 return {element,start:start.toString().length,end:end.toString().length};
}
function restore(saved){
 if(!saved||!saved.element.isConnected)return;
 const nodes=textNodes(saved.element);
 function point(offset){for(const node of nodes){if(offset<=node.length)return [node,offset];offset-=node.length}return [saved.element,saved.element.childNodes.length]}
 const start=point(saved.start),end=point(saved.end),selection=window.getSelection();
 // Most edits do not change the caret nodes. Resetting the selection in that case
 // makes browsers scroll the whole editable paragraph back into view.
 if(selection.rangeCount){const current=selection.getRangeAt(0);if(current.startContainer===start[0]&&current.startOffset===start[1]&&current.endContainer===end[0]&&current.endOffset===end[1])return}
 if(selection.setBaseAndExtent)selection.setBaseAndExtent(start[0],start[1],end[0],end[1]);
 else{const range=document.createRange();range.setStart(...start);range.setEnd(...end);selection.removeAllRanges();selection.addRange(range)}
}

function preserveScroll(root){
 const elements=[];
 for(let node=root.parentElement;node;node=node.parentElement){
  if(node===document.scrollingElement)continue;
  if(node.scrollHeight>node.clientHeight||node.scrollWidth>node.clientWidth)elements.push({node,top:node.scrollTop,left:node.scrollLeft});
 }
 const top=window.scrollY,left=window.scrollX;
 return ()=>{
  for(const entry of elements){if(entry.node.scrollTop!==entry.top)entry.node.scrollTop=entry.top;if(entry.node.scrollLeft!==entry.left)entry.node.scrollLeft=entry.left}
  if(Math.abs(window.scrollY-top)>.5||Math.abs(window.scrollX-left)>.5)window.scrollTo({top,left,behavior:'instant'});
 };
}

function splitOversizedText(element,rootTop,zoom,pageHeight,margin){
 // Work at rendered line boundaries, including when one paragraph spans several pages.
 const pitch=pageHeight+PAGE_GAP;
 for(let pass=0;pass<150;pass++){
  let inserted=false;
  for(const node of textNodes(element)){
   if(!node.length)continue;
   const range=document.createRange();range.selectNodeContents(node);
   const lines=Array.from(range.getClientRects());
   const overflowing=lines.find(rect=>{
    if(!rect.height)return false;
    const top=(rect.top-rootTop)/zoom,bottom=(rect.bottom-rootTop)/zoom;
    const page=Math.max(0,Math.floor((top+.1)/pitch));
    return bottom>page*pitch+pageHeight-margin+.5;
   });
   if(!overflowing)continue;
   let low=0,high=node.length;
   while(low<high){const mid=Math.floor((low+high)/2);range.setStart(node,mid);range.setEnd(node,Math.min(node.length,mid+1));if(range.getBoundingClientRect().top<overflowing.top-.5)low=mid+1;else high=mid}
   const lineTop=(overflowing.top-rootTop)/zoom;
   const page=Math.max(0,Math.floor((lineTop+.1)/pitch));
   const distance=(page+1)*pitch+margin-lineTop;
   if(distance<=0)continue;
   const spacer=document.createElement('span');spacer.dataset.inlinePageBreak='';spacer.contentEditable='false';spacer.setAttribute('aria-hidden','true');
   spacer.style.cssText=`display:block;height:${distance}px;min-height:${distance}px;line-height:0;font-size:0;pointer-events:none;user-select:none;`;
   range.setStart(node,low);range.collapse(true);range.insertNode(spacer);
   inserted=true;break;
  }
  if(!inserted)break;
 }
}

export default function useResumePagination({pageRef,resume,pageHeight,margin,scale,visible,pdfPreview,setPageCount}){
 useLayoutEffect(()=>{
  const root=pageRef.current;
  if(!root||!visible||pdfPreview)return;
  let frame=0,scrollFrame=0,running=false,lastHeight=0,disposed=false,scrollIntent=0;
  const userScroll=()=>{scrollIntent++};
  window.addEventListener('wheel',userScroll,{passive:true});
  window.addEventListener('touchmove',userScroll,{passive:true});
  window.addEventListener('pointerdown',userScroll,{passive:true});
  function paginate(){
   if(disposed||running||!root.isConnected||!root.getBoundingClientRect().width)return;
   running=true;
   const saved=bookmark(root),restoreScroll=preserveScroll(root),intent=scrollIntent;
   root.querySelectorAll('[data-inline-page-break]').forEach(node=>node.remove());
   root.querySelectorAll('[data-page-shift]').forEach(node=>{node.style.removeProperty('padding-top');node.style.removeProperty('--page-padding');delete node.dataset.pageShift});
   root.querySelectorAll('[contenteditable]').forEach(node=>node.normalize());
   const rootTop=root.getBoundingClientRect().top,zoom=root.getBoundingClientRect().width/root.offsetWidth||scale||1,pitch=pageHeight+PAGE_GAP,capacity=pageHeight-2*margin;
   const atoms=Array.from(root.querySelectorAll('.editable-resume-header,.inline-section-header,.inline-entry-heading,.education-two-lines,.inline-bullets>li,.inline-paragraph'));
   for(let index=0;index<atoms.length;index++){
    const atom=atoms[index],rect=atom.getBoundingClientRect();
    if(rect.height<=0)continue;
    let top=(rect.top-rootTop)/zoom,height=rect.height/zoom;
    let page=Math.max(0,Math.floor((top+.1)/pitch));
    const end=page*pitch+pageHeight-margin,start=page*pitch+margin;
    let needed=height;
    if(atom.matches('.inline-section-header,.inline-entry-heading')){
     const next=atoms[index+1];
     if(next){const nextRect=next.getBoundingClientRect();const combined=(nextRect.bottom-rect.top)/zoom;if(combined<=capacity)needed=Math.max(needed,combined)}
    }
    if(top<start-.5||((top+needed>end+.5)&&needed<=capacity)){
     const target=top<start-.5?start:(page+1)*pitch+margin;
     const shift=target-top;
     atom.style.paddingTop=`${shift}px`;atom.style.setProperty('--page-padding',`${shift}px`);atom.dataset.pageShift='';
     top=target;
    }
    if(height>capacity){
     const editable=atom.querySelector('[contenteditable="true"],[contenteditable="false"]');
     if(editable)splitOversizedText(editable,rootTop,zoom,pageHeight,margin);
    }
   }
   const fields=root.querySelector('.document-fields');
   const end=fields?(fields.getBoundingClientRect().bottom-rootTop)/zoom:pageHeight-margin;
   setPageCount(Math.max(1,Math.ceil((end+margin+PAGE_GAP-.5)/pitch)));
   lastHeight=fields?.getBoundingClientRect().height||0;
   restore(saved);
   restoreScroll();
   // Safari/Chromium may reveal a restored selection just after layout. Cancel that
   // deferred scroll, while allowing intentional mouse/touch scrolling to proceed.
   cancelAnimationFrame(scrollFrame);
   scrollFrame=requestAnimationFrame(()=>{if(!disposed&&intent===scrollIntent)restoreScroll()});
   running=false;
  }
  paginate();
  const fields=root.querySelector('.document-fields');
  const observer=new ResizeObserver(()=>{
   if(running||Math.abs((fields?.getBoundingClientRect().height||0)-lastHeight)<.5)return;
   cancelAnimationFrame(frame);frame=requestAnimationFrame(paginate);
  });
  if(fields)observer.observe(fields);
  document.fonts?.ready.then(()=>{if(!disposed&&root.isConnected){cancelAnimationFrame(frame);frame=requestAnimationFrame(paginate)}});
  return()=>{disposed=true;observer.disconnect();cancelAnimationFrame(frame);cancelAnimationFrame(scrollFrame);window.removeEventListener('wheel',userScroll);window.removeEventListener('touchmove',userScroll);window.removeEventListener('pointerdown',userScroll)};
 },[pageRef,resume,pageHeight,margin,scale,visible,pdfPreview,setPageCount]);
}
