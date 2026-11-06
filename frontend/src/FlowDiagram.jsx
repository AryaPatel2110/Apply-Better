import React, {useMemo, useState} from 'react';

const palette={Applied:'#002050','Online Assessment':'#1160b7',Interviewing:'#669ecb',Offer:'#1160b7',Rejected:'#d24726',Ghosted:'#8999ae',Withdrawn:'#b4bdcb'};
export function layoutFlow(data){
 const depths=data.nodes.map(()=>0);
 for(let pass=0;pass<data.nodes.length;pass++)for(const link of data.links)depths[link.target]=Math.max(depths[link.target],depths[link.source]+1);
 const maxDepth=Math.max(1,...depths), width=Math.max(1100,(maxDepth+1)*275);
 const counts=data.nodes.map((_,index)=>Math.max(data.links.filter(l=>l.source===index).reduce((n,l)=>n+l.value,0),data.links.filter(l=>l.target===index).reduce((n,l)=>n+l.value,0)));
 const scale=Math.min(2.5,280/Math.max(1,counts[0]));
 const nodes=data.nodes.map((node,index)=>({...node,index,depth:depths[index],value:counts[index],height:counts[index]*scale,x:150+depths[index]*(width-330)/maxDepth}));
 let height=440;
 for(let depth=0;depth<=maxDepth;depth++){
  let y=45;
  const column=nodes.filter(n=>n.depth===depth).sort((a,b)=>{
   const priority=n=>['Online Assessment','Interviewing'].includes(n.name)?0:n.name==='Offer'?1:n.name==='Ghosted'?3:2;
   return priority(a)-priority(b)||b.value-a.value;
  });
  for(const node of column){node.y=y;y+=node.height+60;}
  height=Math.max(height,y);
 }
 nodes[0].y=(height-nodes[0].height)/2;
 const sourceOffsets=nodes.map(()=>0),targetOffsets=nodes.map(()=>0);
 const links=[...data.links].sort((a,b)=>nodes[a.target].y-nodes[b.target].y).map(link=>{
  const source=nodes[link.source],target=nodes[link.target],thickness=link.value*scale;
  const sy=source.y+sourceOffsets[link.source]+thickness/2,ty=target.y+targetOffsets[link.target]+thickness/2;
  sourceOffsets[link.source]+=thickness;targetOffsets[link.target]+=thickness;
  const sx=source.x+7,tx=target.x,mid=(sx+tx)/2;
  return {...link,sourceNode:source,targetNode:target,thickness,path:`M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}`};
 });
 return {nodes,links,width,height,maxDepth};
}
export default function FlowDiagram({data}){
 const layout=useMemo(()=>layoutFlow(data),[data]),[hover,setHover]=useState(null);
 const total=layout.nodes[0]?.value||0;
 return <div className="flow-diagram"><div className="flow-scroll"><svg viewBox={`0 0 ${layout.width} ${layout.height}`} style={{minWidth:layout.width}} role="img" aria-label="Application flow by recorded stage"><title>Application flow</title><desc>{layout.links.map(l=>`${l.sourceNode.name} to ${l.targetNode.name}: ${l.value}`).join('. ')}</desc>
 {layout.links.map((link,index)=><path key={index} d={link.path} fill="none" stroke={palette[link.targetNode.name]||'#b1d6f0'} strokeWidth={Math.max(2,link.thickness)} opacity={hover?.link===String(index)?0.7:0.42} onMouseEnter={()=>setHover({link:String(index),text:`${link.sourceNode.name} → ${link.targetNode.name}`,value:link.value})} onMouseLeave={()=>setHover(null)}><title>{`${link.sourceNode.name} → ${link.targetNode.name}: ${link.value}`}</title></path>)}
 {layout.nodes.map(node=>{const incoming=layout.links.find(l=>l.target===node.index),parent=incoming?.sourceNode;return <g key={node.key} tabIndex={0} onMouseEnter={()=>setHover({text:node.key.split('/').slice(1).join(' → ')||'Applied',value:node.value})} onMouseLeave={()=>setHover(null)} onFocus={()=>setHover({text:node.key.split('/').slice(1).join(' → ')||'Applied',value:node.value})} onBlur={()=>setHover(null)} aria-label={`${node.name}: ${node.value} applications${parent?`, after ${parent.name}`:''}`}><rect x={node.x} y={node.y} width={7} height={Math.max(2,node.height)} fill={palette[node.name]||'#b1d6f0'}/><text x={node.index===0?node.x-10:node.x+15} y={node.y+node.height/2-3} textAnchor={node.index===0?'end':'start'} className="flow-node-name">{node.name}</text><text x={node.index===0?node.x-10:node.x+15} y={node.y+node.height/2+15} textAnchor={node.index===0?'end':'start'} className="flow-node-value">{node.value}</text><title>{`${node.key.split('/').slice(1).join(' → ')||'Applied'}: ${node.value}`}</title></g>})}
 </svg></div>{hover&&<div className="flow-hover" role="status"><strong>{hover.text}</strong><span>{hover.value} application{hover.value===1?'':'s'} · {Math.round(hover.value/Math.max(1,total)*100)}%</span></div>}</div>
}
