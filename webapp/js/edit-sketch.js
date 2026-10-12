/* Local, editable vector drawing. Only its flattened PNG is sent to generation. */
(function (global) {
  'use strict';
  const TOOLS = [['select','↖','Select'],['pen','✎','Pen'],['pencil','╱','Pencil'],['brush','◒','Brush'],['marker','▰','Marker'],['eraser','▱','Eraser'],['line','╱','Line'],['arrow','➜','Arrow'],['rectangle','□','Rectangle'],['ellipse','○','Ellipse'],['triangle','△','Triangle'],['star','☆','Star'],['text','T','Text'],['sticker','☺','Stickers'],['hand','✥','Pan']];
  const STICKERS = ['🌳','🌲','🌷','🌻','🏠','🏢','🚗','🚲','⛵','🧍','🐈','🐕','🦋','☀️','☁️','⛰️','❤️','⭐'];
  const PALETTE = ['#202534','#ffffff','#ef4444','#f97316','#facc15','#22c55e','#14b8a6','#3b82f6','#8b5cf6','#ec4899','#8b5e3c','#94a3b8'];
  const FREE = new Set(['pen','pencil','brush','marker','eraser']);
  const history = new WeakMap();
  const clamp = (value,min,max) => Math.max(min,Math.min(max,Number(value)||0));
  const copy = value => JSON.parse(JSON.stringify(value));
  const safe = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function create() { return {version:1,width:1024,height:1024,background:'#ffffff',items:[],revision:0,tool:'pen',color:'#202534',fill:'#a7c7f2',filled:false,size:6,opacity:1,text:'Text',sticker:'🌳',editing:true,sourceNodeId:'',sourceRevision:-1}; }
  function validSize(width,height) { return Number.isInteger(width)&&Number.isInteger(height)&&width>=256&&height>=256&&width<=4096&&height<=4096&&width*height<=16777216; }
  function restore(saved) {
    const doc=create();if(!saved||saved.version!==1||!validSize(saved.width,saved.height)||!Array.isArray(saved.items))return doc;
    Object.assign(doc,copy(saved));
    const numeric=(v,min,max)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max;
    doc.items=doc.items.slice(0,500).filter(i=>i&&TOOLS.some(t=>t[0]===i.type)&&!['select','hand'].includes(i.type)&&numeric(i.x,-100000,100000)&&numeric(i.y,-100000,100000)&&numeric(i.size,1,100)&&numeric(i.opacity,0,1)&&numeric(i.sx,.001,1000)&&numeric(i.sy,.001,1000)&&numeric(i.rotation,0,360)&&/^#[0-9a-f]{6}$/i.test(i.color)&&/^#[0-9a-f]{6}$/i.test(i.fill)&&(FREE.has(i.type)?Array.isArray(i.points)&&i.points.length>0&&i.points.length<=4096&&i.points.every(p=>Array.isArray(p)&&p.length===3&&numeric(p[0],-100000,100000)&&numeric(p[1],-100000,100000)&&numeric(p[2],0,1)):numeric(i.w,-100000,100000)&&numeric(i.h,-100000,100000)&&(!['text','sticker'].includes(i.type)||(typeof i.text==='string'&&i.text.length<=320))));
    for(const key of ['color','fill','background'])if(!/^#[0-9a-f]{6}$/i.test(doc[key]))doc[key]=create()[key];
    doc.size=clamp(doc.size,1,100);doc.opacity=clamp(doc.opacity,.05,1);doc.revision=Math.max(0,Number(doc.revision)||0);doc.text=String(doc.text||'Text').slice(0,160);doc.sticker=STICKERS.includes(doc.sticker)?doc.sticker:STICKERS[0];
    if(!TOOLS.some(t=>t[0]===doc.tool))doc.tool='pen';doc.editing=!!doc.editing;
    return doc;
  }
  function hasContent(doc) { return !!doc?.items?.some(item=>item.type!=='eraser'); }
  function documentSnapshot(doc) { return JSON.stringify({width:doc.width,height:doc.height,background:doc.background,items:doc.items}); }
  function historyFor(doc) { if(!history.has(doc))history.set(doc,{undo:[],redo:[]});return history.get(doc); }
  function commit(doc,before) {
    const after=documentSnapshot(doc);if(before===after)return false;
    if(doc.items.length>500||after.length>1500000){Object.assign(doc,JSON.parse(before));throw new Error('This drawing is full. Remove a few objects before adding more.');}
    const h=historyFor(doc);h.undo.push(before);h.redo=[];
    while(h.undo.length>40||h.undo.reduce((n,s)=>n+s.length,0)>8000000)h.undo.shift();
    doc.revision++;return true;
  }
  function undo(doc,redo=false) {
    const h=historyFor(doc),from=redo?h.redo:h.undo,to=redo?h.undo:h.redo;
    if(!from.length)return false;
    to.push(documentSnapshot(doc));Object.assign(doc,JSON.parse(from.pop()));doc.revision++;return true;
  }
  function localBounds(item) {
    const half=(item.size||1)/2;
    if(item.points?.length){const xs=item.points.map(p=>p[0]),ys=item.points.map(p=>p[1]);return {x:Math.min(...xs)-half,y:Math.min(...ys)-half,w:Math.max(...xs)-Math.min(...xs)+2*half,h:Math.max(...ys)-Math.min(...ys)+2*half};}
    return {x:Math.min(0,item.w||0)-half,y:Math.min(0,item.h||0)-half,w:Math.abs(item.w||1)+2*half,h:Math.abs(item.h||1)+2*half};
  }
  function corners(item) {
    const b=localBounds(item),a=(item.rotation||0)*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
    return [[b.x,b.y],[b.x+b.w,b.y],[b.x+b.w,b.y+b.h],[b.x,b.y+b.h]].map(([x,y])=>{x*=item.sx||1;y*=item.sy||1;return {x:item.x+x*c-y*s,y:item.y+x*s+y*c};});
  }
  function bounds(item) { const pts=corners(item),xs=pts.map(p=>p.x),ys=pts.map(p=>p.y);return {x:Math.min(...xs),y:Math.min(...ys),w:Math.max(...xs)-Math.min(...xs),h:Math.max(...ys)-Math.min(...ys)}; }
  function hit(item,point,tolerance=8) {
    const a=-(item.rotation||0)*Math.PI/180,dx=point.x-item.x,dy=point.y-item.y,b=localBounds(item);
    const x=(dx*Math.cos(a)-dy*Math.sin(a))/(item.sx||1),y=(dx*Math.sin(a)+dy*Math.cos(a))/(item.sy||1);
    return x>=b.x-tolerance&&x<=b.x+b.w+tolerance&&y>=b.y-tolerance&&y<=b.y+b.h+tolerance;
  }
  function drawItem(ctx,item) {
    ctx.save();ctx.translate(item.x,item.y);ctx.rotate((item.rotation||0)*Math.PI/180);ctx.scale(item.sx||1,item.sy||1);
    ctx.globalAlpha=item.opacity??1;ctx.lineWidth=item.size||1;ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle=item.color;ctx.fillStyle=item.fill||item.color;
    if(item.type==='eraser')ctx.globalCompositeOperation='destination-out';
    if(FREE.has(item.type)){
      const pts=item.points||[];
      ctx.fillStyle=item.color;
      if(item.type==='pencil')ctx.globalAlpha*=.6;
      if(item.type==='marker')ctx.globalAlpha*=.35;
      if(item.type==='brush'){ctx.shadowColor=item.color;ctx.shadowBlur=(item.size||1)*.2;}
      if(pts.length===1){ctx.beginPath();ctx.arc(pts[0][0],pts[0][1],Math.max(.5,item.size*(pts[0][2]||.5)),0,Math.PI*2);ctx.fill();}
      for(let i=1;i<pts.length;i++){ctx.lineWidth=Math.max(.5,item.size*(item.type==='marker'?1:(pts[i][2]??.5)+.5));ctx.beginPath();ctx.moveTo(pts[i-1][0],pts[i-1][1]);ctx.lineTo(pts[i][0],pts[i][1]);ctx.stroke();}
    }else if(item.type==='text'||item.type==='sticker'){
      ctx.fillStyle=item.color;ctx.textBaseline='top';ctx.font=(item.type==='text'?'600 ':'')+item.h+'px system-ui, "Apple Color Emoji", "Segoe UI Emoji"';
      ctx.fillText(item.text,0,0,item.w);
    }else{
      const w=item.w,h=item.h;ctx.beginPath();
      if(item.type==='line'||item.type==='arrow'){
        ctx.moveTo(0,0);ctx.lineTo(w,h);
        if(item.type==='arrow'){const a=Math.atan2(h,w),r=Math.max(18,item.size*4);ctx.moveTo(w-r*Math.cos(a-.45),h-r*Math.sin(a-.45));ctx.lineTo(w,h);ctx.lineTo(w-r*Math.cos(a+.45),h-r*Math.sin(a+.45));}
      }else if(item.type==='rectangle')ctx.rect(0,0,w,h);
      else if(item.type==='ellipse')ctx.ellipse(w/2,h/2,Math.abs(w)/2,Math.abs(h)/2,0,0,Math.PI*2);
      else if(item.type==='triangle'){ctx.moveTo(w/2,0);ctx.lineTo(w,h);ctx.lineTo(0,h);ctx.closePath();}
      else if(item.type==='star'){for(let i=0;i<10;i++){const a=-Math.PI/2+i*Math.PI/5,r=i%2?.42:1,x=w/2+Math.cos(a)*w/2*r,y=h/2+Math.sin(a)*h/2*r;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.closePath();}
      if(item.filled&&!['line','arrow'].includes(item.type))ctx.fill();ctx.stroke();
    }
    ctx.restore();
  }
  // Erasers act on the artwork layer, never on the background or later strokes.
  const artwork=new WeakMap();
  function paint(canvas,doc,background=true) {
    if(canvas.width!==doc.width)canvas.width=doc.width;if(canvas.height!==doc.height)canvas.height=doc.height;
    if(!artwork.has(canvas))artwork.set(canvas,canvas.ownerDocument.createElement('canvas'));
    const art=artwork.get(canvas);if(art.width!==doc.width)art.width=doc.width;if(art.height!==doc.height)art.height=doc.height;
    const ink=art.getContext('2d',{willReadFrequently:true});ink.clearRect(0,0,doc.width,doc.height);doc.items.forEach(item=>drawItem(ink,item));
    const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.clearRect(0,0,doc.width,doc.height);
    if(background){ctx.fillStyle=doc.background;ctx.fillRect(0,0,doc.width,doc.height);}ctx.drawImage(art,0,0);
    return canvas;
  }
  async function exportPNG(doc,ownerDocument=global.document) {
    if(!hasContent(doc))throw new Error('Draw something before generating.');
    const canvas=paint(ownerDocument.createElement('canvas'),doc);
    const pixels=artwork.get(canvas).getContext('2d').getImageData(0,0,doc.width,doc.height).data;
    let visible=false;for(let i=3;i<pixels.length;i+=4)if(pixels[i]){visible=true;break;}
    if(!visible)throw new Error('The drawing is empty. Add a visible stroke or object before generating.');
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(!blob)throw new Error('Could not prepare the drawing. Please try again.');
    return blob;
  }
  class Editor {
    constructor(host,doc,onChange,onError){
      this.host=host;this.doc=doc;this.onChange=onChange;this.onError=onError;this.selected=-1;this.zoom=1;this.pan={x:0,y:0};this.space=false;this.destroyed=false;this.touches=new Map();
      const button=(action,label)=>'<button type="button" data-action="'+action+'">'+label+'</button>';
      host.innerHTML='<aside class="edit-sketch-tools"><h3>Sketch to Image</h3><p>Draw your idea. Turn it into a realistic photo.</p><div class="edit-sketch-tool-grid" role="group" aria-label="Drawing tools">'+TOOLS.map(([key,icon,label])=>'<button type="button" data-tool="'+key+'" title="'+label+'" aria-label="'+label+'"><b>'+icon+'</b><span>'+label+'</span></button>').join('')+'</div><div class="edit-sketch-color-row"><label>Stroke <input type="color" data-setting="color" aria-label="Stroke color" value="'+safe(doc.color)+'"></label><label>Fill <input type="color" data-setting="fill" aria-label="Fill color" value="'+safe(doc.fill)+'"></label><label><input type="checkbox" data-setting="filled" '+(doc.filled?'checked':'')+'> Fill shapes</label></div><div class="edit-sketch-palette">'+PALETTE.map(color=>'<button type="button" data-color="'+color+'" style="--swatch:'+color+'" aria-label="Use color '+color+'"></button>').join('')+'</div><label class="edit-sketch-range">Size <input aria-label="Brush size" type="range" min="1" max="100" value="'+doc.size+'" data-setting="size"><output data-output="size">'+doc.size+'</output></label><label class="edit-sketch-range">Opacity <input aria-label="Brush opacity" type="range" min="5" max="100" value="'+Math.round(doc.opacity*100)+'" data-setting="opacity"><output data-output="opacity">'+Math.round(doc.opacity*100)+'%</output></label><div class="edit-sketch-text" hidden><label>Text <input type="text" maxlength="160" data-setting="text" aria-label="Drawing text" value="'+safe(doc.text)+'"></label></div><div class="edit-sketch-stickers" role="group" aria-label="Stickers" hidden>'+STICKERS.map((sticker,i)=>'<button type="button" data-sticker="'+i+'" aria-label="Sticker '+safe(sticker)+'">'+sticker+'</button>').join('')+'</div><div class="edit-sketch-object" hidden><span>Selected object</span><div>'+button('duplicate','Duplicate')+button('delete','Delete')+button('backward','Send backward')+button('forward','Bring forward')+button('rotate','Rotate 15°')+'</div><small>Drag to move. Drag the corner to resize.</small></div><details class="edit-sketch-document"><summary>Canvas</summary><div><label>Width <input type="number" min="256" max="4096" value="'+doc.width+'" data-dimension="width" aria-label="Canvas width"></label><label>Height <input type="number" min="256" max="4096" value="'+doc.height+'" data-dimension="height" aria-label="Canvas height"></label></div>'+button('resize','Apply size')+'<label>Background <input type="color" data-setting="background" aria-label="Canvas background" value="'+safe(doc.background)+'"></label></details><div class="edit-sketch-history">'+button('undo','↶ Undo')+button('redo','↷ Redo')+button('clear','Clear canvas')+'</div></aside><section class="edit-sketch-paper-area" aria-label="Drawing workspace"><div class="edit-sketch-view-controls">'+button('zoom-out','−')+button('fit','Fit')+button('zoom-in','+')+'<output data-zoom></output></div><div class="edit-sketch-paper"><canvas class="edit-sketch-canvas" tabindex="0" aria-label="Drawing canvas"></canvas><canvas class="edit-sketch-selection" aria-hidden="true"></canvas></div><small class="edit-sketch-hint">Draw with mouse, touch or pen · Space + drag to pan · Ctrl / ⌘ + scroll to zoom</small></section>';
      this.area=host.querySelector('.edit-sketch-paper-area');this.paper=host.querySelector('.edit-sketch-paper');this.canvas=host.querySelector('.edit-sketch-canvas');this.overlay=host.querySelector('.edit-sketch-selection');
      this.click=e=>{const t=e.target.closest('button');if(!t)return;if(t.dataset.tool)this.chooseTool(t.dataset.tool);else if(t.dataset.color)this.setting('color',t.dataset.color);else if(t.dataset.sticker!==undefined){doc.sticker=STICKERS[Number(t.dataset.sticker)];this.chooseTool('sticker');}else if(t.dataset.action)this.action(t.dataset.action);};
      this.input=e=>{const key=e.target.dataset.setting;if(key)this.setting(key,e.target.type==='checkbox'?e.target.checked:e.target.value);};
      host.addEventListener('click',this.click);host.addEventListener('input',this.input);
      this.down=e=>this.pointerDown(e);this.move=e=>this.pointerMove(e);this.up=e=>this.pointerEnd(e,false);this.cancel=e=>this.pointerEnd(e,true);
      this.area.addEventListener('pointerdown',this.down);this.area.addEventListener('pointermove',this.move);this.area.addEventListener('pointerup',this.up);this.area.addEventListener('pointercancel',this.cancel);this.area.addEventListener('lostpointercapture',this.cancel);
      this.wheel=e=>{if(e.target.closest('button,input'))return;e.preventDefault();if(e.ctrlKey||e.metaKey)this.setZoom(this.zoom*Math.exp(-e.deltaY*.005),e.clientX,e.clientY);else{this.pan.x-=e.deltaX;this.pan.y-=e.deltaY;this.layout();}};
      this.area.addEventListener('wheel',this.wheel,{passive:false});
      this.key=e=>this.keyDown(e);this.keyup=e=>{if(e.code==='Space'){this.space=false;this.area.classList.remove('is-panning');}};
      this.blur=()=>{this.space=false;this.area.classList.remove('is-panning');if(this.drag)this.pointerEnd({pointerId:this.drag.id},true);this.pinch=null;this.touches.clear();};
      global.document.addEventListener('keydown',this.key);global.document.addEventListener('keyup',this.keyup);global.addEventListener('blur',this.blur);
      this.resizeObserver=new ResizeObserver(()=>this.fit());this.resizeObserver.observe(this.area);
      this.sync();this.fit();this.draw();
      // Paint once more after the mounted canvas receives its layout. This
      // also restores the bitmap when switching back from generated results.
      this.requestDraw();
    }
    chooseTool(tool){if(!TOOLS.some(t=>t[0]===tool))return;this.doc.tool=tool;this.selected=-1;this.sync();this.drawOverlay();this.changed(false);}
    setting(key,value){
      const d=this.doc,before=documentSnapshot(d);
      if(['color','fill','background'].includes(key)&&/^#[0-9a-f]{6}$/i.test(value))d[key]=value;
      else if(key==='filled')d[key]=!!value;
      else if(key==='size')d.size=clamp(value,1,100);
      else if(key==='opacity')d.opacity=clamp(value,5,100)/100;
      else if(key==='text')d.text=String(value).slice(0,160);
      const item=d.items[this.selected];
      if(item&&['color','fill','filled','size','opacity'].includes(key))item[key]=d[key];
      if(item?.type==='text'&&key==='text')item.text=d.text;
      this.finishChange(before);this.sync();this.draw();
    }
    action(action){
      const d=this.doc,before=documentSnapshot(d),item=d.items[this.selected];
      if(action==='fit'){this.fit();return;}if(action==='zoom-in'||action==='zoom-out'){this.setZoom(this.zoom*(action==='zoom-in'?1.2:1/1.2));return;}
      if(action==='undo'||action==='redo'){const w=d.width,h=d.height;if(undo(d,action==='redo')){this.selected=-1;this.draw();this.sync();if(d.width!==w||d.height!==h)this.fit();this.changed();}return;}
      if(action==='clear'){d.items=[];this.selected=-1;}
      else if(action==='resize'){
        const w=Number(this.host.querySelector('[data-dimension="width"]').value),h=Number(this.host.querySelector('[data-dimension="height"]').value);
        if(!validSize(w,h)){this.onError('Use whole canvas dimensions from 256 to 4096 px.');return;}
        // Scale the drawing with its document, preserving all editable objects.
        d.items.forEach(i=>{i.x*=w/d.width;i.y*=h/d.height;i.sx=(i.sx||1)*w/d.width;i.sy=(i.sy||1)*h/d.height;});d.width=w;d.height=h;this.fit();
      }else if(item){
        if(action==='delete'){d.items.splice(this.selected,1);this.selected=-1;}
        if(action==='duplicate'){const clone=copy(item);clone.x+=24;clone.y+=24;d.items.push(clone);this.selected=d.items.length-1;}
        if(action==='rotate')item.rotation=((item.rotation||0)+15)%360;
        if(action==='forward'&&this.selected<d.items.length-1){d.items.splice(this.selected,1);d.items.splice(++this.selected,0,item);}
        if(action==='backward'&&this.selected>0){d.items.splice(this.selected,1);d.items.splice(--this.selected,0,item);}
      }
      this.finishChange(before);this.sync();this.draw();
    }
    changed(){this.onChange?.();}
    finishChange(before){try{commit(this.doc,before);}catch(e){this.onError(e.message);}this.changed();}
    sync(){
      const d=this.doc,h=historyFor(d),item=d.items[this.selected];
      this.host.querySelectorAll('[data-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool===d.tool)));
      this.host.querySelectorAll('[data-sticker]').forEach(b=>b.setAttribute('aria-pressed',String(STICKERS[Number(b.dataset.sticker)]===d.sticker)));
      this.host.querySelectorAll('[data-setting]').forEach(input=>{const k=input.dataset.setting,v=k==='opacity'?Math.round(d.opacity*100):d[k];if(input.type==='checkbox')input.checked=!!v;else if(global.document.activeElement!==input)input.value=v;});
      this.host.querySelector('[data-output="size"]').textContent=d.size;
      this.host.querySelector('[data-output="opacity"]').textContent=Math.round(d.opacity*100)+'%';
      this.host.querySelector('.edit-sketch-text').hidden=d.tool!=='text'&&item?.type!=='text';
      this.host.querySelector('.edit-sketch-stickers').hidden=d.tool!=='sticker';this.host.querySelector('.edit-sketch-object').hidden=!item;
      this.host.querySelector('[data-action="undo"]').disabled=!h.undo.length;this.host.querySelector('[data-action="redo"]').disabled=!h.redo.length;
      this.host.querySelector('[data-action="clear"]').disabled=!d.items.length;
      this.host.querySelectorAll('[data-dimension]').forEach(input=>{if(global.document.activeElement!==input)input.value=d[input.dataset.dimension];});
      this.area.dataset.tool=d.tool;
    }
    fit(){const r=this.area.getBoundingClientRect();this.zoom=Math.min((r.width-64)/this.doc.width,(r.height-64)/this.doc.height);this.zoom=Math.max(.05,this.zoom);this.pan={x:0,y:0};this.layout();}
    setZoom(value,cx,cy){const r=this.area.getBoundingClientRect(),old=this.zoom;this.zoom=clamp(value,.05,8);const x=(cx??r.left+r.width/2)-r.left-r.width/2,y=(cy??r.top+r.height/2)-r.top-r.height/2;this.pan.x=x-(x-this.pan.x)*this.zoom/old;this.pan.y=y-(y-this.pan.y)*this.zoom/old;this.layout();}
    layout(){this.paper.style.width=this.doc.width+'px';this.paper.style.height=this.doc.height+'px';this.paper.style.transform='translate(calc(-50% + '+this.pan.x+'px),calc(-50% + '+this.pan.y+'px)) scale('+this.zoom+')';this.host.querySelector('[data-zoom]').textContent=Math.round(this.zoom*100)+'%';this.drawOverlay();}
    point(e){const r=this.canvas.getBoundingClientRect();return {x:Math.round((e.clientX-r.left)/this.zoom*10)/10,y:Math.round((e.clientY-r.top)/this.zoom*10)/10,p:e.pointerType==='pen'?Math.round(clamp(e.pressure,.05,1)*100)/100:.5};}
    pointerDown(e){
      if(this.host.inert||e.target.closest('button,input')||e.button>1)return;
      if(e.pointerType==='touch'){
        this.touches.set(e.pointerId,{x:e.clientX,y:e.clientY});
        if(this.touches.size===2){
          const points=new Map(this.touches);if(this.drag){Object.assign(this.doc,JSON.parse(this.drag.before));this.drag=null;this.draw();this.sync();}
          const [a,b]=[...points.values()];this.pinch={distance:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y)),zoom:this.zoom,mid:{x:(a.x+b.x)/2,y:(a.y+b.y)/2},pan:{...this.pan}};
          this.area.setPointerCapture(e.pointerId);e.preventDefault();return;
        }
      }
      if(this.drag||this.pinch)return;
      const onPaper=e.target===this.canvas,p=this.point(e),d=this.doc;
      if(!onPaper&&!this.space&&d.tool!=='hand'&&e.button!==1)return;
      e.preventDefault();this.canvas.focus({preventScroll:true});this.area.setPointerCapture(e.pointerId);
      this.drag={id:e.pointerId,start:p,before:documentSnapshot(d),x:e.clientX,y:e.clientY,pan:{...this.pan}};
      if(this.space||d.tool==='hand'||e.button===1){this.drag.kind='pan';return;}
      if(d.tool==='select'){
        const selected=d.items[this.selected],b=selected&&bounds(selected),handle=b&&Math.hypot(p.x-b.x-b.w,p.y-b.y-b.h)<12/this.zoom;
        if(handle){this.drag.kind='scale';this.drag.item=copy(selected);this.drag.bounds=b;return;}
        this.selected=-1;for(let i=d.items.length-1;i>=0;i--)if(d.items[i].type!=='eraser'&&hit(d.items[i],p,6/this.zoom)){this.selected=i;break;}
        if(this.selected>=0){this.drag.kind='move';this.drag.item=copy(d.items[this.selected]);const item=this.drag.item;for(const key of ['color','fill','filled','size','opacity'])d[key]=item[key];if(item.type==='text')d.text=item.text;}
        this.sync();this.drawOverlay();return;
      }
      if(d.items.length>=500){this.pointerEnd(e,true);this.onError('This drawing is full. Remove an object to continue.');return;}
      const item={type:d.tool,x:p.x,y:p.y,sx:1,sy:1,rotation:0,size:d.size,color:d.color,fill:d.fill,filled:d.filled,opacity:d.opacity};
      if(FREE.has(d.tool))item.points=[[0,0,p.p]];
      else if(d.tool==='text'||d.tool==='sticker'){item.text=d.tool==='text'?(d.text||'Text'):d.sticker;item.h=d.tool==='text'?Math.max(24,d.size*5):128;item.w=d.tool==='text'?Math.max(item.h,item.h*.65*Array.from(item.text).length):128;}
      else{item.w=0;item.h=0;}
      d.items.push(item);this.drag.kind='draw';this.drag.index=d.items.length-1;this.draw();
    }
    pointerMove(e){
      if(this.touches.has(e.pointerId))this.touches.set(e.pointerId,{x:e.clientX,y:e.clientY});
      if(this.pinch&&this.touches.size>=2){
        e.preventDefault();const [a,b]=[...this.touches.values()],p=this.pinch,r=this.area.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2;
        this.zoom=clamp(p.zoom*Math.hypot(a.x-b.x,a.y-b.y)/p.distance,.05,8);const factor=this.zoom/p.zoom;
        this.pan={x:(a.x+b.x)/2-cx-(p.mid.x-cx-p.pan.x)*factor,y:(a.y+b.y)/2-cy-(p.mid.y-cy-p.pan.y)*factor};this.layout();return;
      }
      const drag=this.drag;if(!drag||drag.id!==e.pointerId)return;e.preventDefault();const d=this.doc,p=this.point(e);
      if(drag.kind==='pan'){this.pan.x=drag.pan.x+e.clientX-drag.x;this.pan.y=drag.pan.y+e.clientY-drag.y;this.layout();return;}
      if(drag.kind==='move'){Object.assign(d.items[this.selected],{x:drag.item.x+p.x-drag.start.x,y:drag.item.y+p.y-drag.start.y});}
      else if(drag.kind==='scale'){
        const b=drag.bounds,f=clamp(1+((p.x-drag.start.x)+(p.y-drag.start.y))/Math.max(1,b.w+b.h),.05,20);Object.assign(d.items[this.selected],{sx:clamp(drag.item.sx*f,.001,1000),sy:clamp(drag.item.sy*f,.001,1000)});
      }else if(drag.kind==='draw'){
        const item=d.items[drag.index];
        if(FREE.has(item.type)){
          const coalesced=e.getCoalescedEvents?.();for(const event of coalesced?.length?coalesced:[e]){const q=this.point(event),last=item.points.at(-1);if(item.points.length<4096&&Math.hypot(q.x-item.x-last[0],q.y-item.y-last[1])>.5)item.points.push([Math.round((q.x-item.x)*10)/10,Math.round((q.y-item.y)*10)/10,q.p]);}
        }else if(!['text','sticker'].includes(item.type)){
          let w=p.x-drag.start.x,h=p.y-drag.start.y;if(e.shiftKey){const size=Math.max(Math.abs(w),Math.abs(h));w=Math.sign(w||1)*size;h=Math.sign(h||1)*size;}
          if(['line','arrow'].includes(item.type)){item.w=w;item.h=h;}else{item.x=drag.start.x+Math.min(w,0);item.y=drag.start.y+Math.min(h,0);item.w=Math.abs(w);item.h=Math.abs(h);}
        }
      }
      this.requestDraw();
    }
    pointerEnd(e,cancel){
      this.touches.delete(e.pointerId);
      if(this.pinch){if(this.touches.size<2)this.pinch=null;if(this.area.hasPointerCapture?.(e.pointerId))this.area.releasePointerCapture(e.pointerId);return;}
      const drag=this.drag;if(!drag||drag.id!==e.pointerId)return;this.drag=null;
      if(this.area.hasPointerCapture?.(drag.id))this.area.releasePointerCapture(drag.id);
      if(cancel)Object.assign(this.doc,JSON.parse(drag.before));
      else if(drag.kind!=='pan'){
        const item=this.doc.items[drag.index];if(drag.kind==='draw'&&item&&!item.points&&!['text','sticker'].includes(item.type)&&Math.hypot(item.w,item.h)<2)this.doc.items.splice(drag.index,1);
        this.finishChange(drag.before);
      }
      this.draw();this.sync();
    }
    keyDown(e){
      if(this.host.inert||e.target.closest('input,textarea,select,[contenteditable="true"]')||!this.host.isConnected)return;
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();this.action(e.shiftKey?'redo':'undo');}
      else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();this.action('redo');}
      else if(e.code==='Space'){e.preventDefault();this.space=true;this.area.classList.add('is-panning');}
      else if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();this.action('delete');}
      else if(e.key==='Escape'){if(this.drag)this.pointerEnd({pointerId:this.drag.id},true);this.selected=-1;this.sync();this.drawOverlay();}
      else if(['v','p','b','e','h'].includes(e.key.toLowerCase())&&!e.metaKey&&!e.ctrlKey)this.chooseTool(({v:'select',p:'pen',b:'brush',e:'eraser',h:'hand'})[e.key.toLowerCase()]);
    }
    requestDraw(){if(!this.frame)this.frame=requestAnimationFrame(()=>{this.frame=0;if(!this.destroyed)this.draw();});}
    draw(){paint(this.canvas,this.doc);this.drawOverlay();}
    drawOverlay(){
      this.overlay.width=this.doc.width;this.overlay.height=this.doc.height;
      const item=this.doc.items[this.selected];if(!item)return;
      const c=this.overlay.getContext('2d'),b=bounds(item),unit=1/this.zoom;c.strokeStyle='#296ce8';c.lineWidth=1.5*unit;c.setLineDash([5*unit,3*unit]);c.strokeRect(b.x,b.y,b.w,b.h);c.setLineDash([]);c.fillStyle='#ffffff';c.fillRect(b.x+b.w-5*unit,b.y+b.h-5*unit,10*unit,10*unit);c.strokeRect(b.x+b.w-5*unit,b.y+b.h-5*unit,10*unit,10*unit);
    }
    destroy(){
      if(this.drag)this.pointerEnd({pointerId:this.drag.id},true);this.destroyed=true;cancelAnimationFrame(this.frame);this.resizeObserver.disconnect();
      this.touches.clear();this.pinch=null;
      this.host.removeEventListener('click',this.click);this.host.removeEventListener('input',this.input);this.area.removeEventListener('wheel',this.wheel);
      for(const [type,fn] of [['pointerdown',this.down],['pointermove',this.move],['pointerup',this.up],['pointercancel',this.cancel],['lostpointercapture',this.cancel]])this.area.removeEventListener(type,fn);
      global.document.removeEventListener('keydown',this.key);global.document.removeEventListener('keyup',this.keyup);global.removeEventListener('blur',this.blur);
    }
  }
  global.SYLVEXSketch={create,restore,validSize,hasContent,documentSnapshot,commit,undo,localBounds,bounds,hit,drawItem,paint,exportPNG,Editor};
})(typeof window==='undefined'?globalThis:window);
