// Deterministic force step: springs for relations, repulsion and label clearance.
// Presentation hierarchy only: category links are not prerequisites.
export function radialLayout(nodes) {
  const positions=new Map(), hubs=new Map(), links=[];
  const categories=[...new Set(nodes.map(n=>n.topic))].sort((a,b)=>a-b);
  categories.forEach((topic,index)=>{
    const group=nodes.filter(n=>n.topic===topic),angle=-5*Math.PI/6+index*2*Math.PI/categories.length;
    const hub={x:360*Math.cos(angle),y:360*Math.sin(angle)};hubs.set(topic,hub);
    group.forEach((n,i)=>{
      const theta=angle+2*Math.PI*i/group.length;
      const p={x:hub.x+180*Math.cos(theta),y:hub.y+180*Math.sin(theta)};
      positions.set(n.id,p);links.push({topic,id:n.id});
    });
  });
  return {positions,hubs,links,center:{x:0,y:0}};
}

export function relaxCategory(points, edges, pinned=null, strength=1) {
  const byId=new Map(points.map(p=>[p.id,p]));
  const forces=new Map(points.map(p=>[p.id,{x:(p.homeX-p.x)*.003,y:(p.homeY-p.y)*.003}]));
  for(const e of edges){
    const a=byId.get(e.from),b=byId.get(e.to);if(!a||!b)continue;
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;
    const rest=Math.hypot(b.homeX-a.homeX,b.homeY-a.homeY);
    const force=(d-rest)*.035;
    forces.get(a.id).x+=dx/d*force;forces.get(a.id).y+=dy/d*force;
    forces.get(b.id).x-=dx/d*force;forces.get(b.id).y-=dy/d*force;
  }
  for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){
    const a=points[i],b=points[j];let dx=b.x-a.x,dy=b.y-a.y;
    if(Math.abs(dx)+Math.abs(dy)<.01){dx=(j-i)*.1;dy=1}
    const distance=Math.hypot(dx,dy),overlap=Math.max(0,1-Math.hypot(dx/165,dy/110))*6;
    forces.get(a.id).x-=dx/distance*overlap;forces.get(a.id).y-=dy/distance*overlap;
    forces.get(b.id).x+=dx/distance*overlap;forces.get(b.id).y+=dy/distance*overlap;
  }
  for(const p of points){if(p.id===pinned)continue;const f=forces.get(p.id);p.x+=Math.max(-9,Math.min(9,f.x))*strength;p.y+=Math.max(-9,Math.min(9,f.y))*strength}
}

export function interpolateCamera(from,to,progress){
  const t=Math.max(0,Math.min(1,progress)),ease=t*t*t*(t*(t*6-15)+10);
  if(t===0)return {...from};if(t===1)return {...to};
  const k=from.k+(to.k-from.k)*ease;
  // Interpolate the screen transform, so zoom and pan follow one straight path.
  return {x:(from.x*from.k+(to.x*to.k-from.x*from.k)*ease)/k,y:(from.y*from.k+(to.y*to.k-from.y*from.k)*ease)/k,k};
}

export function resizeCamera(camera,oldWidth,oldHeight,width,height){
  return {...camera,x:camera.x+(width-oldWidth)/(2*camera.k),y:camera.y+(height-oldHeight)/(2*camera.k)};
}

export function relax(points, edges, pinned=null, strength=1) {
  const forces=new Map(points.map(p=>[p.id,{x:0,y:0}]));
  const byId=new Map(points.map(p=>[p.id,p]));
  for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){
    const a=points[i],b=points[j];let dx=b.x-a.x,dy=b.y-a.y;
    if(Math.abs(dx)+Math.abs(dy)<.01){dx=(j-i)*.1;dy=.5}
    const d=Math.hypot(dx,dy),f=Math.min(5,2500/(d*d));
    const clearance=Math.max(0,1-Math.hypot(dx/155,dy/60))*3;
    const fx=dx/d*(f+clearance),fy=dy/d*(f+clearance);
    forces.get(a.id).x-=fx;forces.get(a.id).y-=fy;
    forces.get(b.id).x+=fx;forces.get(b.id).y+=fy;
  }
  for(const e of edges){
    const a=byId.get(e.from),b=byId.get(e.to);if(!a||!b)continue;
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1,f=(d-160)*.018;
    forces.get(a.id).x+=dx/d*f;forces.get(a.id).y+=dy/d*f;
    forces.get(b.id).x-=dx/d*f;forces.get(b.id).y-=dy/d*f;
  }
  let movement=0;
  for(const p of points){if(p.id===pinned)continue;const f=forces.get(p.id);
    f.x+=(495-p.x)*.002;f.y+=(267-p.y)*.002;
    const dx=Math.max(-7,Math.min(7,f.x))*strength,dy=Math.max(-7,Math.min(7,f.y))*strength;
    p.x+=dx;p.y+=dy;movement+=Math.abs(dx)+Math.abs(dy);
  }
  return movement;
}

// Layer by directed prerequisite relations; cycles stay together in a finite layer.
// This is display-only and does not change learning recommendations or edge review status.
export function logicLayout(nodes, edges) {
  const ids=new Set(nodes.map(n=>n.id)), indegree=new Map(nodes.map(n=>[n.id,0]));
  const links=edges.filter(e=>ids.has(e.source_node_id)&&ids.has(e.target_node_id));
  const directed=links.filter(e=>e.relation_type==='prerequisite');
  const outgoing=new Map(nodes.map(n=>[n.id,[]])),rank=new Map(nodes.map(n=>[n.id,0]));
  for(const e of directed){outgoing.get(e.source_node_id).push(e.target_node_id);indegree.set(e.target_node_id,indegree.get(e.target_node_id)+1)}
  const queue=nodes.filter(n=>indegree.get(n.id)===0).map(n=>n.id);
  for(let i=0;i<queue.length;i++){const id=queue[i];for(const target of outgoing.get(id)){rank.set(target,Math.max(rank.get(target),rank.get(id)+1));indegree.set(target,indegree.get(target)-1);if(indegree.get(target)===0)queue.push(target)}}
  const layers=new Map();for(const n of nodes){const level=rank.get(n.id);if(!layers.has(level))layers.set(level,[]);layers.get(level).push(n)}
  const positions=new Map();let row=0;
  for(const [,group] of [...layers].sort((a,b)=>a[0]-b[0])){group.sort((a,b)=>a.topic-b.topic||a.id.localeCompare(b.id));for(let offset=0;offset<group.length;offset+=5){const line=group.slice(offset,offset+5);line.forEach((n,i)=>positions.set(n.id,{x:(i-(line.length-1)/2)*230,y:row*180}));row++}}
  for(const p of positions.values())p.y-=(row-1)*90;
  return {positions,links};
}

export function logicNeighborhood(id, edges) {
  const links=edges.filter(e=>e.source_node_id===id||e.target_node_id===id);
  return {ids:new Set([id,...links.flatMap(e=>[e.source_node_id,e.target_node_id])]),links};
}
export function logicRelationLabel(edge, active=null) {
  if(edge.relation_type==='prerequisite')return active===edge.target_node_id?'前置知识':active===edge.source_node_id?'后续知识':'前置 → 后续';
  if(edge.relation_type==='confusable_with')return '易混辨析';
  if(edge.relation_type==='related_to'&&[edge.source_node_id,edge.target_node_id].sort().join('|')==='C-013|C-014')return '不同方法';
  return '相关知识';
}
