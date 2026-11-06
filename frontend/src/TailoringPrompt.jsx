import React,{useEffect,useRef,useState} from 'react';
import {Copy,Check} from 'lucide-react';
import template from './prompts/resume-tailoring.txt?raw';

const headings={summary:'SUMMARY',experience:'PROFESSIONAL EXPERIENCE',education:'EDUCATION',projects:'PROJECTS',skills:'SKILLS',volunteering:'VOLUNTEERING',achievements:'ACHIEVEMENTS',certifications:'CERTIFICATIONS',publications:'PUBLICATIONS',additional:'ADDITIONAL INFORMATION'};
export function resumeText(resume){
 if(!resume)return '';
 const parts=[resume.name,[resume.phone,resume.email,resume.location,resume.website].filter(Boolean).join(' | '),...(resume.links||[]).map(link=>[link.label,link.url].filter(Boolean).join(': '))].filter(Boolean);
 for(const section of resume.section_order||[]){
  const value=resume[section];
  const content=Array.isArray(value)?value.map(entry=>[
   [section==='education'?entry.organization:entry.title,section==='education'?entry.title:entry.organization,entry.location,entry.dates].filter(Boolean).join(' | '),
   entry.gpa?`GPA: ${entry.gpa}`:'',
   ...(entry.description||'').split('\n').filter(line=>line.trim()).map(line=>'• '+line.replace(/^[•-]\s*/,''))
  ].filter(Boolean).join('\n')).filter(Boolean).join('\n\n'):(value||'');
  if(content.trim())parts.push(`${headings[section]||section}\n${content}`);
 }
 return parts.join('\n\n');
}

export default function TailoringPrompt({resume,jobDescription=''}){
 const currentResume=resumeText(resume);
 const prompt=template.replace(/\[Resume\]|\[JD\]/g,token=>token==='[Resume]'?currentResume:jobDescription);
 const ready=Boolean(resume?.name?.trim()&&jobDescription.trim());
 const [copied,setCopied]=useState(false),[error,setError]=useState('');
 const text=useRef(null);
 useEffect(()=>{setCopied(false);setError('')},[prompt]);
 async function copy(){
  setError('');setCopied(false);
  try{
   if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(prompt);
   else{
    const temporary=document.createElement('textarea');temporary.value=prompt;temporary.style.position='fixed';temporary.style.opacity='0';document.body.appendChild(temporary);
    try{temporary.select();if(!document.execCommand('copy'))throw Error('Copy unavailable')}finally{temporary.remove()}
   }
   setCopied(true);
  }catch{
   const range=document.createRange();range.selectNodeContents(text.current);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
   setError('Automatic copy is unavailable. The prompt is selected; press Ctrl+C or Command+C to copy.');
  }
 }
 return <section className="tailoring-prompt" aria-labelledby="tailoring-prompt-heading"><div className="tailoring-prompt-heading"><h3 id="tailoring-prompt-heading">Tailoring prompt</h3><button type="button" className="secondary" onClick={copy} disabled={!ready}>{copied?<Check size={15}/>:<Copy size={15}/>} {copied?'Copied':'Copy prompt'}</button></div><p>Your current resume and job description are filled in automatically. Edits update this prompt.</p><pre ref={text} tabIndex={0}>{prompt}</pre><span role="status">{error||(copied?'Prompt copied to clipboard.':!ready?'Select a resume and enter a job description to copy the prompt.':'')}</span></section>;
}
