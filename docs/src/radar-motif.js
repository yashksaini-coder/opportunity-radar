// Deterministic radar motif shared by banner.html and banner-social.html.
// Rings + crosshair (the dashboard logo), a sweep wedge, category-coloured
// blips, and one red "broken" blip whose repair arc turns green.
function drawRadar(g,{cx,cy,R,sweepDeg}){
  let s=11;const rnd=()=>{s=(s*16807)%2147483647;return (s-1)/2147483646};
  const ns='http://www.w3.org/2000/svg';
  const el=(t,a)=>{const e=document.createElementNS(ns,t);for(const k in a)e.setAttribute(k,a[k]);g.appendChild(e);return e};
  const blue='#2a78d6',ink='#0c0e11',red='#d03b3b',green='#1baf7a';
  const cat={hackathon:blue,scholarship:'#eb6834',job:green};
  const rad=d=>d*Math.PI/180;
  // soft glow behind the dish
  el('circle',{cx,cy,r:R*1.35,fill:'url(#glow)'});
  // rings (dashboard logo ratios 10 : 6.5 : 3)
  for(const f of [1,0.65,0.3]) el('circle',{cx,cy,r:R*f,stroke:blue,'stroke-opacity':f===1?0.55:0.35,'stroke-width':f===1?1.6:1.1});
  // faint intermediate rings
  for(const f of [0.825,0.475]) el('circle',{cx,cy,r:R*f,stroke:ink,'stroke-opacity':0.07,'stroke-width':1,'stroke-dasharray':'3 5'});
  // crosshair + diagonals
  for(const a of [0,45,90,135]){const x=Math.cos(rad(a))*R,y=Math.sin(rad(a))*R;
    el('line',{x1:cx-x,y1:cy-y,x2:cx+x,y2:cy+y,stroke:a%90?ink:blue,'stroke-opacity':a%90?0.10:0.35,'stroke-width':1})}
  // sweep wedge: 70deg, fading behind the leading edge
  const a0=rad(sweepDeg),a1=rad(sweepDeg-70);
  const p=`M${cx},${cy} L${cx+Math.cos(a0)*R},${cy+Math.sin(a0)*R} A${R},${R} 0 0 0 ${cx+Math.cos(a1)*R},${cy+Math.sin(a1)*R} Z`;
  const sw=g.ownerDocument.getElementById('sweep');
  sw.setAttribute('x1',cx+Math.cos(a0)*R);sw.setAttribute('y1',cy+Math.sin(a0)*R);
  sw.setAttribute('x2',cx+Math.cos(a1)*R);sw.setAttribute('y2',cy+Math.sin(a1)*R);
  el('path',{d:p,fill:'url(#sweep)'});
  el('line',{x1:cx,y1:cy,x2:cx+Math.cos(a0)*R,y2:cy+Math.sin(a0)*R,stroke:blue,'stroke-width':2.2,'stroke-opacity':0.9,'stroke-linecap':'round'});
  // blips: opportunities, coloured by category (scholarship-heavy like the real data)
  const cats=['scholarship','scholarship','scholarship','scholarship','hackathon','hackathon','job'];
  const blips=[];
  for(let i=0;i<22;i++){const a=rnd()*360,r=R*(0.18+Math.pow(rnd(),0.8)*0.78);
    const x=cx+Math.cos(rad(a))*r,y=cy+Math.sin(rad(a))*r;
    if(blips.some(b=>Math.hypot(b.x-x,b.y-y)<22))continue;
    if(Math.hypot(x-(cx+Math.cos(rad(150))*R*0.62),y-(cy+Math.sin(rad(150))*R*0.62+14))<58)continue; // keep the broken blip + label clear
    blips.push({x,y,c:cat[cats[Math.floor(rnd()*cats.length)]],big:rnd()<0.3})}
  for(const b of blips){
    if(b.big)el('circle',{cx:b.x,cy:b.y,r:11,fill:b.c,'fill-opacity':0.16,filter:'url(#soft)'});
    el('circle',{cx:b.x,cy:b.y,r:b.big?5:3.6,fill:b.c,stroke:'#fcfcfb','stroke-width':1.5})}
  // the broken blip: red, hollow, with a repair arc that runs red -> amber -> green
  const ba=rad(150),br=R*0.62,bx=cx+Math.cos(ba)*br,by=cy+Math.sin(ba)*br;
  el('circle',{cx:bx,cy:by,r:13,fill:red,'fill-opacity':0.14,filter:'url(#soft)'});
  el('circle',{cx:bx,cy:by,r:6,fill:'#fcfcfb',stroke:red,'stroke-width':2.4});
  el('line',{x1:bx-3,y1:by-3,x2:bx+3,y2:by+3,stroke:red,'stroke-width':1.8,'stroke-linecap':'round'});
  el('line',{x1:bx+3,y1:by-3,x2:bx-3,y2:by+3,stroke:red,'stroke-width':1.8,'stroke-linecap':'round'});
  // repair arc: 270deg around the blip, gradient along it
  const ar=22,sa=rad(200),ea=rad(200+270);
  const rp=g.ownerDocument.getElementById('repair');
  rp.setAttribute('x1',bx+Math.cos(sa)*ar);rp.setAttribute('y1',by+Math.sin(sa)*ar);
  rp.setAttribute('x2',bx+Math.cos(ea)*ar);rp.setAttribute('y2',by+Math.sin(ea)*ar);
  el('path',{d:`M${bx+Math.cos(sa)*ar},${by+Math.sin(sa)*ar} A${ar},${ar} 0 1 1 ${bx+Math.cos(ea)*ar},${by+Math.sin(ea)*ar}`,stroke:'url(#repair)','stroke-width':3,'stroke-linecap':'round'});
  // healed endpoint: green dot with a check
  const hx=bx+Math.cos(ea)*ar,hy=by+Math.sin(ea)*ar;
  el('circle',{cx:hx,cy:hy,r:7,fill:green});
  el('path',{d:`M${hx-3.2},${hy+0.2} l2.2,2.2 l4.2,-4.6`,stroke:'#fcfcfb','stroke-width':1.9,'stroke-linecap':'round','stroke-linejoin':'round'});
  // mono labels at the healed blip and on the outer ring
  const lbl=(x,y,t,c,anchor)=>{const e=el('text',{x,y,fill:c,'font-family':'JetBrains Mono, monospace','font-size':11,'letter-spacing':'0.06em','text-anchor':anchor||'start'});e.textContent=t};
  lbl(bx-30,by+42,'0 → 92 rows · HEALED',green,'start');
  lbl(cx+R+4,cy-R-8,'nightly 03:00 IST','#898781','end');
  // centre dot
  el('circle',{cx,cy,r:3,fill:blue});
}
