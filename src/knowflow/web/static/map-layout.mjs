// Deterministic force step: springs for relations, repulsion and label clearance.
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
