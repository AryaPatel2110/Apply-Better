import {normalizeApplication} from './history.js';
// Keep each path separate: rejection after OA is distinct from rejection after interview.
// Prefix nodes also keep the diagram acyclic when a paused application resumes.
export function applicationFlow(rows) {
  const nodes = [{name:'Applied',key:'root'}], links = [], indices = new Map([['root',0]]), edges = new Map();
  for (const row of rows) {
    const history = normalizeApplication(row).status_history;
    const path = history.map(event=>event.status).filter((status,index,all)=>index===0||status!==all[index-1]);
    if (path[0] === 'Applied') path.shift();
    else path.unshift('Prior stages unknown');
    if (!path.length) path.push('Awaiting response');
    let prefix = 'root', source = 0;
    for (const status of path) {
      prefix += '/' + status;
      if (!indices.has(prefix)) {
        indices.set(prefix,nodes.length);
        nodes.push({name:status,key:prefix});
      }
      const target = indices.get(prefix), edgeKey = `${source}:${target}`;
      if (!edges.has(edgeKey)) {
        edges.set(edgeKey,links.length);
        links.push({source,target,value:0});
      }
      links[edges.get(edgeKey)].value++;
      source = target;
    }
    // Preserve flow conservation when some applications remain at an intermediate stage.
    if (['Online Assessment','Interviewing','Applied'].includes(path.at(-1))) {
      const name = path.at(-1)==='Online Assessment'?'OA in progress':'Interview in progress';
      const leafKey = prefix+'/current';
      if (!indices.has(leafKey)) {indices.set(leafKey,nodes.length);nodes.push({name,key:leafKey});}
      const target=indices.get(leafKey), edgeKey=`${source}:${target}`;
      if (!edges.has(edgeKey)) {edges.set(edgeKey,links.length);links.push({source,target,value:0});}
      links[edges.get(edgeKey)].value++;
    }
  }
  return {nodes,links};
}
