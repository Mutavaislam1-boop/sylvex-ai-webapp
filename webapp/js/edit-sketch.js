/* Local, editable vector drawing. Only its flattened PNG is sent to generation. */
(function (global) {
  'use strict';
  const TOOLS = [['select','↖','Select'],['pen','✒','Pen'],['pencil','✎','Pencil'],['brush','●','Brush'],['marker','▬','Marker'],['eraser','▱','Eraser'],['line','╱','Line'],['arrow','➜','Arrow'],['rectangle','▭','Rectangle'],['ellipse','○','Ellipse'],['triangle','△','Triangle'],['star','☆','Star'],['diamond','◇','Diamond'],['pentagon','⬠','Pentagon'],['hexagon','⬡','Hexagon'],['cross','✚','Cross'],['speech','▱','Speech bubble'],['text','T','Text'],['sticker','☺','Stickers'],['hand','✥','Pan']];
  const CORE_STICKERS = ['🌳','🏠','🚗','🧍','🐈','☀️'];
  const EXTRA_STICKERS = ['🌲','🌷','🌻','🏢','🚲','⛵','🐕','🦋','☁️','⛰️','❤️','⭐','🌙','🔥','🎈','🎁','🎵','📍','💬','✨','🍎','☕','📷','💡'];
  const STICKERS = [...CORE_STICKERS,...EXTRA_STICKERS];
  const PALETTE = ['#202534','#ffffff','#ef4444','#f97316','#facc15','#22c55e','#14b8a6','#3b82f6','#8b5cf6','#ec4899','#8b5e3c','#94a3b8'];
  const FREE = new Set(['pen','pencil','brush','marker','eraser']);
  const DRAW_TOOLS = ['pen','pencil','brush','marker','eraser'];
  const CORE_SHAPES = ['line','arrow','rectangle','ellipse','triangle','star'];
  const EXTRA_SHAPES = ['diamond','pentagon','hexagon','cross','speech'];
  const SHAPE_TOOLS = [...CORE_SHAPES,...EXTRA_SHAPES];
  const TOOL_INFO = Object.fromEntries(TOOLS.map(item=>[item[0],item]));
  const RESIZE_HANDLES = ['nw','n','ne','e','se','s','sw','w'];
  const history = new WeakMap();
  const clamp = (value,min,max) => Math.max(min,Math.min(max,Number(value)||0));
  const copy = value => JSON.parse(JSON.stringify(value));
  const safe = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function create() { return {version:1,width:1024,height:1024,background:'#ffffff',items:[],revision:0,tool:'pen',color:'#202534',fill:'#a7c7f2',filled:false,size:6,opacity:1,text:'Text',sticker:'🌳',editing:true,referenceUrl:'',referencePreview:'',referenceKey:'',referenceNodeId:'',flattenedUrl:'',flattenedRevision:-1,flattenedReferenceKey:'',sourceNodeId:'',sourceRevision:-1}; }
  function validSize(width,height) { return Number.isInteger(width)&&Number.isInteger(height)&&width>=256&&height>=256&&width<=4096&&height<=4096&&width*height<=16777216; }
  function restore(saved) {
    const doc=create();if(!saved||saved.version!==1||!validSize(saved.width,saved.height)||!Array.isArray(saved.items))return doc;
    Object.assign(doc,copy(saved));
    const numeric=(v,min,max)=>typeof v==='number'&&Number.isFinite(v)&&v>=min&&v<=max;
    doc.items=doc.items.slice(0,500).filter(i=>i&&TOOLS.some(t=>t[0]===i.type)&&!['select','hand'].includes(i.type)&&numeric(i.x,-100000,100000)&&numeric(i.y,-100000,100000)&&numeric(i.size,1,100)&&numeric(i.opacity,0,1)&&numeric(i.sx,.001,1000)&&numeric(i.sy,.001,1000)&&numeric(i.rotation,0,360)&&/^#[0-9a-f]{6}$/i.test(i.color)&&/^#[0-9a-f]{6}$/i.test(i.fill)&&(FREE.has(i.type)?Array.isArray(i.points)&&i.points.length>0&&i.points.length<=4096&&i.points.every(p=>Array.isArray(p)&&p.length===3&&numeric(p[0],-100000,100000)&&numeric(p[1],-100000,100000)&&numeric(p[2],0,1)):numeric(i.w,-100000,100000)&&numeric(i.h,-100000,100000)&&(!['text','sticker'].includes(i.type)||(typeof i.text==='string'&&i.text.length<=320))));
    for(const key of ['color','fill','background'])if(!/^#[0-9a-f]{6}$/i.test(doc[key]))doc[key]=create()[key];
    doc.size=clamp(doc.size,1,100);doc.opacity=clamp(doc.opacity,.05,1);doc.revision=Math.max(0,Number(doc.revision)||0);doc.text=String(doc.text||'Text').slice(0,160);doc.sticker=STICKERS.includes(doc.sticker)?doc.sticker:STICKERS[0];
    for(const key of ['referenceUrl','referencePreview','referenceKey','referenceNodeId','flattenedUrl','flattenedReferenceKey','sourceNodeId'])doc[key]=typeof doc[key]==='string'&&doc[key].length<=8192?doc[key]:'';
    doc.flattenedRevision=Number.isInteger(doc.flattenedRevision)?doc.flattenedRevision:-1;doc.sourceRevision=Number.isInteger(doc.sourceRevision)?doc.sourceRevision:-1;
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
  function textAt(doc,point,tolerance=8) { for(let i=doc.items.length-1;i>=0;i--)if(doc.items[i].type==='text'&&hit(doc.items[i],point,tolerance))return i;return -1; }
  function textWidth(text,height) { return Math.max(Number(height)||24,(Number(height)||24)*.65*Math.max(1,Array.from(String(text||' ')).length)); }
  function worldPoint(item,point) {
    const a=(item.rotation||0)*Math.PI/180,c=Math.cos(a),s=Math.sin(a),x=point.x*(item.sx||1),y=point.y*(item.sy||1);
    return {x:item.x+x*c-y*s,y:item.y+x*s+y*c};
  }
  function selectionFrame(item,zoom=1) {
    const b=localBounds(item),points={
      nw:{x:b.x,y:b.y},n:{x:b.x+b.w/2,y:b.y},ne:{x:b.x+b.w,y:b.y},e:{x:b.x+b.w,y:b.y+b.h/2},
      se:{x:b.x+b.w,y:b.y+b.h},s:{x:b.x+b.w/2,y:b.y+b.h},sw:{x:b.x,y:b.y+b.h},w:{x:b.x,y:b.y+b.h/2},
    };
    for(const key of Object.keys(points))points[key]=worldPoint(item,points[key]);
    const center=worldPoint(item,{x:b.x+b.w/2,y:b.y+b.h/2}),top=points.n,dx=top.x-center.x,dy=top.y-center.y,length=Math.hypot(dx,dy)||1;
    points.rotate={x:top.x+dx/length*32/zoom,y:top.y+dy/length*32/zoom};
    return {bounds:b,points,center,corners:[points.nw,points.ne,points.se,points.sw]};
  }
  function oppositeAnchor(bounds,handle) {
    const horizontal=handle.includes('w')?bounds.x+bounds.w:handle.includes('e')?bounds.x:bounds.x+bounds.w/2;
    const vertical=handle.includes('n')?bounds.y+bounds.h:handle.includes('s')?bounds.y:bounds.y+bounds.h/2;
    return {x:horizontal,y:vertical};
  }
  function resizeItem(item,startItem,handle,pointer) {
    const b=localBounds(startItem),anchorLocal=oppositeAnchor(b,handle),anchorWorld=worldPoint(startItem,anchorLocal),a=-(startItem.rotation||0)*Math.PI/180;
    const dx=pointer.x-anchorWorld.x,dy=pointer.y-anchorWorld.y,q={x:dx*Math.cos(a)-dy*Math.sin(a),y:dx*Math.sin(a)+dy*Math.cos(a)};
    let sx=startItem.sx||1,sy=startItem.sy||1;
    if(handle.includes('e'))sx=clamp(q.x/(b.x+b.w-anchorLocal.x),.001,1000);
    if(handle.includes('w'))sx=clamp(q.x/(b.x-anchorLocal.x),.001,1000);
    if(handle.includes('s'))sy=clamp(q.y/(b.y+b.h-anchorLocal.y),.001,1000);
    if(handle.includes('n'))sy=clamp(q.y/(b.y-anchorLocal.y),.001,1000);
    const rotation=(startItem.rotation||0)*Math.PI/180,c=Math.cos(rotation),s=Math.sin(rotation);
    Object.assign(item,{sx,sy,x:anchorWorld.x-(anchorLocal.x*sx*c-anchorLocal.y*sy*s),y:anchorWorld.y-(anchorLocal.x*sx*s+anchorLocal.y*sy*c)});
    return item;
  }
  function rotateItem(item,degrees,centerWorld) {
    const b=localBounds(item),centerLocal={x:b.x+b.w/2,y:b.y+b.h/2},center=centerWorld||worldPoint(item,centerLocal),rotation=((degrees%360)+360)%360,a=rotation*Math.PI/180,c=Math.cos(a),s=Math.sin(a);
    item.rotation=rotation;item.x=center.x-(centerLocal.x*(item.sx||1)*c-centerLocal.y*(item.sy||1)*s);item.y=center.y-(centerLocal.x*(item.sx||1)*s+centerLocal.y*(item.sy||1)*c);
    return item;
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
      else if(item.type==='diamond'){ctx.moveTo(w/2,0);ctx.lineTo(w,h/2);ctx.lineTo(w/2,h);ctx.lineTo(0,h/2);ctx.closePath();}
      else if(item.type==='pentagon'||item.type==='hexagon'){
        const sides=item.type==='pentagon'?5:6;for(let i=0;i<sides;i++){const a=-Math.PI/2+i*Math.PI*2/sides,x=w/2+Math.cos(a)*w/2,y=h/2+Math.sin(a)*h/2;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.closePath();
      }else if(item.type==='cross'){
        ctx.moveTo(w*.34,0);ctx.lineTo(w*.66,0);ctx.lineTo(w*.66,h*.34);ctx.lineTo(w,h*.34);ctx.lineTo(w,h*.66);ctx.lineTo(w*.66,h*.66);ctx.lineTo(w*.66,h);ctx.lineTo(w*.34,h);ctx.lineTo(w*.34,h*.66);ctx.lineTo(0,h*.66);ctx.lineTo(0,h*.34);ctx.lineTo(w*.34,h*.34);ctx.closePath();
      }else if(item.type==='speech'){
        ctx.moveTo(0,0);ctx.lineTo(w,0);ctx.lineTo(w,h*.72);ctx.lineTo(w*.62,h*.72);ctx.lineTo(w*.45,h);ctx.lineTo(w*.45,h*.72);ctx.lineTo(0,h*.72);ctx.closePath();
      }
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
  function referenceSource(doc) { return String(doc?.referencePreview||doc?.referenceUrl||''); }
  function loadReferenceImage(source,ownerDocument=global.document) {
    return new Promise((resolve,reject)=>{
      const ImageClass=ownerDocument?.defaultView?.Image||global.Image;if(!ImageClass)return reject(new Error('Could not load the source image.'));
      const image=new ImageClass();image.crossOrigin='anonymous';image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('Could not load the source image for drawing. Please try again.'));image.src=source;
    });
  }
  async function exportPNG(doc,ownerDocument=global.document) {
    if(!hasContent(doc))throw new Error('Draw something before generating.');
    const source=referenceSource(doc),canvas=paint(ownerDocument.createElement('canvas'),doc,!source);
    const pixels=artwork.get(canvas).getContext('2d').getImageData(0,0,doc.width,doc.height).data;
    let visible=false;for(let i=3;i<pixels.length;i+=4)if(pixels[i]){visible=true;break;}
    if(!visible)throw new Error('The drawing is empty. Add a visible stroke or object before generating.');
    if(source){
      const image=await loadReferenceImage(source,ownerDocument),ctx=canvas.getContext('2d',{willReadFrequently:true}),art=artwork.get(canvas);
      ctx.clearRect(0,0,doc.width,doc.height);ctx.drawImage(image,0,0,doc.width,doc.height);ctx.drawImage(art,0,0);
    }
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(!blob)throw new Error('Could not prepare the drawing. Please try again.');
    return blob;
  }
  class Editor {
    constructor(host,doc,onChange,onError){
      this.host=host;this.doc=doc;this.onChange=onChange;this.onError=onError;this.selected=-1;this.zoom=1;this.pan={x:0,y:0};this.space=false;this.destroyed=false;this.touches=new Map();
      const button=(action,label,title=label)=>'<button type="button" data-action="'+action+'" title="'+title+'" aria-label="'+title+'">'+label+'</button>';
      const toolButton=key=>{const [,icon,label]=TOOL_INFO[key];return '<button type="button" data-tool="'+key+'" title="'+label+'" aria-label="'+label+'"><b>'+icon+'</b><span>'+label+'</span></button>';};
      const stickerButton=(sticker,i)=>'<button type="button" data-sticker="'+i+'" title="Add '+safe(sticker)+'" aria-label="Add '+safe(sticker)+'">'+sticker+'</button>';
      const toolMenu=(group,label,icon,content)=>{
        let primary=content,more='',moreLabel='';
        if(group==='shape'){primary=CORE_SHAPES.map(toolButton).join('');more=EXTRA_SHAPES.map(toolButton).join('');moreLabel='More shapes';}
        if(group==='element'){primary=CORE_STICKERS.map((sticker,i)=>stickerButton(sticker,i)).join('');more=EXTRA_STICKERS.map((sticker,i)=>stickerButton(sticker,CORE_STICKERS.length+i)).join('');moreLabel='More stickers';}
        const menuIcon=group==='draw'?'✒':group==='shape'?'◇':icon;
        return '<details class="edit-sketch-tool-menu" data-tool-group="'+group+'"><summary aria-label="'+label+' tools"><b data-group-icon>'+menuIcon+'</b><span data-group-label>'+label+'</span><i>⌄</i></summary><div class="edit-sketch-tool-popover"><div class="edit-sketch-tool-strip" role="menu">'+primary+'</div>'+(more?'<section class="edit-sketch-more"><span>'+moreLabel+'</span><div>'+more+'</div></section>':'')+'</div></details>';
      };
      const stickerButtons=STICKERS.map(stickerButton).join('');
      host.innerHTML='<section class="edit-sketch-paper-area" aria-label="Drawing workspace"><div class="edit-sketch-view-controls">'+button('zoom-out','−','Zoom out')+button('fit','Fit','Fit canvas')+button('zoom-in','+','Zoom in')+'<output data-zoom></output></div><div class="edit-sketch-paper"><img class="edit-sketch-reference" alt="" crossorigin="anonymous" hidden><canvas class="edit-sketch-canvas" tabindex="0" aria-label="Drawing canvas"></canvas><canvas class="edit-sketch-selection" aria-hidden="true"></canvas><div class="edit-sketch-transform" hidden>'+RESIZE_HANDLES.map(handle=>'<button type="button" class="edit-sketch-handle edit-sketch-handle-'+handle+'" data-transform="'+handle+'" aria-label="Resize '+handle+'"></button>').join('')+'<div class="edit-sketch-floating-actions">'+button('duplicate','⧉','Duplicate')+'<button type="button" data-transform="rotate" title="Drag to rotate" aria-label="Drag to rotate">↻</button>'+button('delete','×','Delete')+'</div></div><input class="edit-sketch-inline-text" maxlength="160" aria-label="Edit drawing text" hidden></div><small class="edit-sketch-hint">Draw with mouse, touch or pen · Double-click text to edit · Space + drag to pan</small></section><aside class="edit-sketch-tools"><header><h3>Sketch to Image</h3><p>Draw your idea. Turn it into a realistic photo.</p></header><div class="edit-sketch-primary-tools" role="group" aria-label="Drawing tools">'+toolButton('select')+toolMenu('draw','Draw','✎',DRAW_TOOLS.map(toolButton).join(''))+toolMenu('shape','Shapes','□',SHAPE_TOOLS.map(toolButton).join(''))+toolMenu('element','Elements','☺',stickerButtons)+toolButton('text')+toolButton('hand')+'</div><details class="edit-sketch-style" open><summary>Style</summary><div class="edit-sketch-color-row"><label>Stroke <input type="color" data-setting="color" aria-label="Stroke color" value="'+safe(doc.color)+'"></label><label>Fill <input type="color" data-setting="fill" aria-label="Fill color" value="'+safe(doc.fill)+'"></label><label><input type="checkbox" data-setting="filled" '+(doc.filled?'checked':'')+'> Fill</label></div><div class="edit-sketch-palette">'+PALETTE.map(color=>'<button type="button" data-color="'+color+'" style="--swatch:'+color+'" aria-label="Use color '+color+'"></button>').join('')+'</div><label class="edit-sketch-range">Size <input aria-label="Brush size" type="range" min="1" max="100" value="'+doc.size+'" data-setting="size"><output data-output="size">'+doc.size+'</output></label><label class="edit-sketch-range">Opacity <input aria-label="Brush opacity" type="range" min="5" max="100" value="'+Math.round(doc.opacity*100)+'" data-setting="opacity"><output data-output="opacity">'+Math.round(doc.opacity*100)+'%</output></label><div class="edit-sketch-text" hidden><label>Text <input type="text" maxlength="160" data-setting="text" aria-label="Drawing text" value="'+safe(doc.text)+'"></label></div></details><div class="edit-sketch-object" hidden><span>Selected object <output data-rotation-output>0°</output></span><div>'+button('backward','Send backward')+button('forward','Bring forward')+'</div><small>Drag to move. Use any edge or corner to resize. Drag ↻ to rotate.</small></div><details class="edit-sketch-document"><summary>Canvas</summary><div><label>Width <input type="number" min="256" max="4096" value="'+doc.width+'" data-dimension="width" aria-label="Canvas width"></label><label>Height <input type="number" min="256" max="4096" value="'+doc.height+'" data-dimension="height" aria-label="Canvas height"></label></div>'+button('resize','Apply size')+'<label>Background <input type="color" data-setting="background" aria-label="Canvas background" value="'+safe(doc.background)+'"></label></details><div class="edit-sketch-history">'+button('undo','↶ Undo')+button('redo','↷ Redo')+button('clear','Clear canvas')+'</div></aside>';
      this.area=host.querySelector('.edit-sketch-paper-area');this.paper=host.querySelector('.edit-sketch-paper');this.reference=host.querySelector('.edit-sketch-reference');this.canvas=host.querySelector('.edit-sketch-canvas');this.overlay=host.querySelector('.edit-sketch-selection');this.transform=host.querySelector('.edit-sketch-transform');this.inline=host.querySelector('.edit-sketch-inline-text');
      host.querySelector('.edit-sketch-hint').textContent='Draw with mouse, touch or pen · Click text again to edit · Space + drag to pan';
      this.positionMenus=()=>{const outer=host.getBoundingClientRect(),panel=host.querySelector('.edit-sketch-tools')?.getBoundingClientRect();if(!panel)return;this.menus.forEach(({menu,popover})=>{if(!menu.open)return;const summary=menu.querySelector('summary').getBoundingClientRect();popover.hidden=false;const top=clamp(summary.top-outer.top,8,Math.max(8,outer.height-popover.offsetHeight-8));popover.style.left=Math.round(panel.left-outer.left-popover.offsetWidth)+'px';popover.style.top=Math.round(top)+'px';});};
      this.closeMenus=()=>this.menus.forEach(({menu})=>menu.removeAttribute('open'));
      this.menus=[...host.querySelectorAll('.edit-sketch-tool-menu')].map(menu=>{const popover=menu.querySelector('.edit-sketch-tool-popover'),entry={menu,popover};popover.dataset.toolPopover=menu.dataset.toolGroup;popover.hidden=true;host.appendChild(popover);entry.toggle=()=>{if(menu.open){this.menus.forEach(other=>{if(other.menu!==menu)other.menu.removeAttribute('open');});popover.hidden=false;requestAnimationFrame(()=>this.positionMenus());}else popover.hidden=true;};menu.addEventListener('toggle',entry.toggle);return entry;});
      this.click=e=>{const t=e.target.closest('button');if(!t)return;if(t.dataset.tool){this.chooseTool(t.dataset.tool);this.closeMenus();}else if(t.dataset.color)this.setting('color',t.dataset.color);else if(t.dataset.sticker!==undefined){doc.sticker=STICKERS[Number(t.dataset.sticker)];this.chooseTool('sticker');this.closeMenus();}else if(t.dataset.action)this.action(t.dataset.action);};
      this.input=e=>{const key=e.target.dataset.setting;if(key)this.setting(key,e.target.type==='checkbox'?e.target.checked:e.target.value);};
      host.addEventListener('click',this.click);host.addEventListener('input',this.input);
      this.down=e=>this.pointerDown(e);this.move=e=>this.pointerMove(e);this.up=e=>this.pointerEnd(e,false);this.cancel=e=>this.pointerEnd(e,true);
      this.area.addEventListener('pointerdown',this.down);this.area.addEventListener('pointermove',this.move);this.area.addEventListener('pointerup',this.up);this.area.addEventListener('pointercancel',this.cancel);this.area.addEventListener('lostpointercapture',this.cancel);
      this.dblclick=e=>this.doubleClick(e);this.area.addEventListener('dblclick',this.dblclick);
      this.inlineKey=e=>{if(e.key==='Enter'){e.preventDefault();this.finishTextEdit(false);}else if(e.key==='Escape'){e.preventDefault();e.stopPropagation();this.finishTextEdit(true);}};
      this.inlineInput=()=>{const item=this.doc.items[this.editingText?.index];if(item)this.inline.style.width=Math.ceil(textWidth(this.inline.value,item.h)+10)+'px';};
      this.inlineBlur=()=>this.finishTextEdit(false);this.inline.addEventListener('keydown',this.inlineKey);this.inline.addEventListener('input',this.inlineInput);this.inline.addEventListener('blur',this.inlineBlur);
      this.wheel=e=>{if(e.target.closest('button,input,summary')&&!e.ctrlKey&&!e.metaKey)return;e.preventDefault();if(e.ctrlKey||e.metaKey)this.setZoom(this.zoom*Math.exp(-e.deltaY*.005),e.clientX,e.clientY);else{this.pan.x-=e.deltaX;this.pan.y-=e.deltaY;this.layout();}};
      this.area.addEventListener('wheel',this.wheel,{passive:false});
      this.gestureStart=e=>{e.preventDefault();const r=this.area.getBoundingClientRect();this.gesture={zoom:this.zoom,x:Number.isFinite(e.clientX)?e.clientX:r.left+r.width/2,y:Number.isFinite(e.clientY)?e.clientY:r.top+r.height/2};};
      this.gestureChange=e=>{if(!this.gesture)return;e.preventDefault();this.setZoom(this.gesture.zoom*clamp(e.scale,.1,10),Number.isFinite(e.clientX)?e.clientX:this.gesture.x,Number.isFinite(e.clientY)?e.clientY:this.gesture.y);};
      this.gestureEnd=e=>{if(this.gesture)e.preventDefault();this.gesture=null;};
      this.area.addEventListener('gesturestart',this.gestureStart,{passive:false});this.area.addEventListener('gesturechange',this.gestureChange,{passive:false});this.area.addEventListener('gestureend',this.gestureEnd,{passive:false});
      this.key=e=>this.keyDown(e);this.keyup=e=>{if(e.code==='Space'){this.space=false;this.area.classList.remove('is-panning');}};
      this.blur=()=>{this.space=false;this.area.classList.remove('is-panning');if(this.drag)this.pointerEnd({pointerId:this.drag.id},true);this.pinch=null;this.gesture=null;this.touches.clear();};
      global.document.addEventListener('keydown',this.key);global.document.addEventListener('keyup',this.keyup);global.addEventListener('blur',this.blur);
      this.resizeObserver=new ResizeObserver(()=>this.fit());this.resizeObserver.observe(this.area);
      this.sync();this.fit();this.draw();
      // Paint once more after the mounted canvas receives its layout. This
      // also restores the bitmap when switching back from generated results.
      this.requestDraw();
    }
    chooseTool(tool){if(!TOOLS.some(t=>t[0]===tool))return;if(this.editingText)this.finishTextEdit(false);this.doc.tool=tool;this.selected=-1;this.sync();this.drawOverlay();this.changed(false);}
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
        if(action==='rotate')rotateItem(item,(item.rotation||0)+15);
        if(action==='forward'&&this.selected<d.items.length-1){d.items.splice(this.selected,1);d.items.splice(++this.selected,0,item);}
        if(action==='backward'&&this.selected>0){d.items.splice(this.selected,1);d.items.splice(--this.selected,0,item);}
      }
      this.finishChange(before);this.sync();this.draw();
    }
    doubleClick(e){
      if(this.host.inert||this.editingText||e.target.closest('button,input')||e.button!==0)return;
      const p=this.point(e),d=this.doc,index=textAt(d,p,6/this.zoom);
      if(index<0)return;e.preventDefault();e.stopPropagation();d.tool='select';this.selected=index;this.editText(index);
    }
    editText(index){
      if(this.editingText)this.finishTextEdit(false);const item=this.doc.items[index];if(!item||item.type!=='text')return;
      this.editingText={index,before:documentSnapshot(this.doc)};this.inline.hidden=false;this.inline.value=item.text;this.inline.style.left=item.x+'px';this.inline.style.top=item.y+'px';this.inline.style.width=Math.ceil(textWidth(item.text,item.h)+10)+'px';this.inline.style.height=Math.max(24,item.h)+'px';this.inline.style.fontSize=item.h+'px';this.inline.style.color=item.color;this.inline.style.transform='rotate('+(item.rotation||0)+'deg) scale('+(item.sx||1)+','+(item.sy||1)+')';
      this.sync();this.drawOverlay();this.inline.focus({preventScroll:true});this.inline.select();
    }
    finishTextEdit(cancel){
      const edit=this.editingText;if(!edit)return;this.editingText=null;this.inline.removeEventListener('blur',this.inlineBlur);
      const item=this.doc.items[edit.index];
      if(cancel)Object.assign(this.doc,JSON.parse(edit.before));
      else if(item){item.text=String(this.inline.value||'Text').slice(0,160);item.w=textWidth(item.text,item.h);this.doc.text=item.text;this.finishChange(edit.before);}
      this.inline.hidden=true;this.inline.style.transform='';this.inline.addEventListener('blur',this.inlineBlur);this.sync();this.draw();
    }
    changed(){this.onChange?.();}
    finishChange(before){try{commit(this.doc,before);}catch(e){this.onError(e.message);}this.changed();}
    sync(){
      const d=this.doc,h=historyFor(d),item=d.items[this.selected];
      this.host.querySelectorAll('[data-tool]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool===d.tool)));
      this.host.querySelectorAll('[data-sticker]').forEach(b=>b.setAttribute('aria-pressed',String(STICKERS[Number(b.dataset.sticker)]===d.sticker)));
      this.host.querySelectorAll('[data-tool-group]').forEach(menu=>{
        const group=menu.dataset.toolGroup,active=group==='draw'?DRAW_TOOLS.includes(d.tool):group==='shape'?SHAPE_TOOLS.includes(d.tool):d.tool==='sticker';
        const summary=menu.querySelector('summary');summary.setAttribute('aria-pressed',String(active));
        if(active){menu.querySelector('[data-group-label]').textContent=d.tool==='sticker'?'Elements':TOOL_INFO[d.tool][2];menu.querySelector('[data-group-icon]').textContent=d.tool==='sticker'?d.sticker:TOOL_INFO[d.tool][1];}
        else{menu.querySelector('[data-group-label]').textContent=group==='draw'?'Draw':group==='shape'?'Shapes':'Elements';menu.querySelector('[data-group-icon]').textContent=group==='draw'?'✒':group==='shape'?'◇':'☺';}
      });
      this.host.querySelectorAll('[data-setting]').forEach(input=>{const k=input.dataset.setting,v=k==='opacity'?Math.round(d.opacity*100):d[k];if(input.type==='checkbox')input.checked=!!v;else if(global.document.activeElement!==input)input.value=v;});
      this.host.querySelector('[data-output="size"]').textContent=d.size;
      this.host.querySelector('[data-output="opacity"]').textContent=Math.round(d.opacity*100)+'%';
      this.host.querySelector('.edit-sketch-text').hidden=d.tool!=='text'&&item?.type!=='text';
      this.host.querySelector('.edit-sketch-object').hidden=!item;
      this.host.querySelector('[data-rotation-output]').textContent=Math.round(item?.rotation||0)+'°';
      this.host.querySelector('[data-action="undo"]').disabled=!h.undo.length;this.host.querySelector('[data-action="redo"]').disabled=!h.redo.length;
      this.host.querySelector('[data-action="clear"]').disabled=!d.items.length;
      this.host.querySelectorAll('[data-dimension]').forEach(input=>{if(global.document.activeElement!==input)input.value=d[input.dataset.dimension];});
      this.area.dataset.tool=d.tool;this.layoutSelectionControls();
    }
    fit(){const r=this.area.getBoundingClientRect(),tools=this.host.querySelector('.edit-sketch-tools'),covered=tools?tools.getBoundingClientRect().width+48:0,usable=Math.max(280,r.width-covered);this.zoom=Math.min((usable-64)/this.doc.width,(r.height-220)/this.doc.height);this.zoom=Math.max(.05,this.zoom);this.pan={x:-covered/2,y:-40};this.layout();}
    setZoom(value,cx,cy){const r=this.area.getBoundingClientRect(),old=this.zoom;this.zoom=clamp(value,.05,8);const x=(cx??r.left+r.width/2)-r.left-r.width/2,y=(cy??r.top+r.height/2)-r.top-r.height/2;this.pan.x=x-(x-this.pan.x)*this.zoom/old;this.pan.y=y-(y-this.pan.y)*this.zoom/old;this.layout();}
    layout(){this.paper.style.width=this.doc.width+'px';this.paper.style.height=this.doc.height+'px';this.paper.style.transform='translate(calc(-50% + '+this.pan.x+'px),calc(-50% + '+this.pan.y+'px)) scale('+this.zoom+')';this.host.querySelector('[data-zoom]').textContent=Math.round(this.zoom*100)+'%';this.drawOverlay();this.layoutSelectionControls();this.positionMenus?.();}
    layoutSelectionControls(){
      const item=this.doc.items[this.selected];if(!item||this.editingText){this.transform.hidden=true;return;}
      const frame=selectionFrame(item,this.zoom);this.transform.hidden=false;
      RESIZE_HANDLES.forEach(handle=>{const control=this.transform.querySelector('[data-transform="'+handle+'"]'),point=frame.points[handle];control.style.left=point.x+'px';control.style.top=point.y+'px';control.style.setProperty('--edit-sketch-control-scale',1/this.zoom);});
      const actions=this.transform.querySelector('.edit-sketch-floating-actions');actions.style.left=frame.points.rotate.x+'px';actions.style.top=frame.points.rotate.y+'px';actions.style.setProperty('--edit-sketch-control-scale',1/this.zoom);
    }
    point(e){const r=this.canvas.getBoundingClientRect();return {x:Math.round((e.clientX-r.left)/this.zoom*10)/10,y:Math.round((e.clientY-r.top)/this.zoom*10)/10,p:e.pointerType==='pen'?Math.round(clamp(e.pressure,.05,1)*100)/100:.5};}
    pointerDown(e){
      const transform=e.target.closest?.('[data-transform]');if(this.host.inert||e.target===this.inline||(!transform&&e.target.closest('button,input'))||e.button>1)return;
      if(e.pointerType==='touch'){
        this.touches.set(e.pointerId,{x:e.clientX,y:e.clientY});
        this.area.setPointerCapture(e.pointerId);e.preventDefault();
        if(this.touches.size===2){
          const points=new Map(this.touches);if(this.drag){Object.assign(this.doc,JSON.parse(this.drag.before));this.drag=null;this.draw();this.sync();}
          const [a,b]=[...points.values()];this.pinch={distance:Math.max(1,Math.hypot(a.x-b.x,a.y-b.y)),zoom:this.zoom,mid:{x:(a.x+b.x)/2,y:(a.y+b.y)/2},pan:{...this.pan}};
          return;
        }
      }
      if(this.drag||this.pinch)return;
      const onPaper=e.target===this.canvas,p=this.point(e),d=this.doc;
      if(!onPaper&&!transform&&!this.space&&d.tool!=='hand'&&e.button!==1)return;
      e.preventDefault();this.canvas.focus({preventScroll:true});this.area.setPointerCapture(e.pointerId);
      if(onPaper&&!transform&&d.tool==='text'){
        const index=textAt(d,p,6/this.zoom);if(index>=0){this.area.releasePointerCapture(e.pointerId);this.selected=index;this.editText(index);return;}
      }
      this.drag={id:e.pointerId,start:p,before:documentSnapshot(d),x:e.clientX,y:e.clientY,pan:{...this.pan}};
      if(transform&&this.selected>=0){
        const item=d.items[this.selected];this.drag.item=copy(item);this.drag.handle=transform.dataset.transform;
        if(this.drag.handle==='rotate'){const frame=selectionFrame(item,this.zoom);this.drag.kind='rotate';this.drag.center=frame.center;this.drag.angle=Math.atan2(p.y-frame.center.y,p.x-frame.center.x);this.drag.rotation=item.rotation||0;}
        else this.drag.kind='resize';
        return;
      }
      if(this.space||d.tool==='hand'||e.button===1){this.drag.kind='pan';return;}
      if(d.tool==='select'){
        this.selected=-1;for(let i=d.items.length-1;i>=0;i--)if(d.items[i].type!=='eraser'&&hit(d.items[i],p,6/this.zoom)){this.selected=i;break;}
        if(this.selected>=0){this.drag.kind='move';this.drag.item=copy(d.items[this.selected]);const item=this.drag.item;for(const key of ['color','fill','filled','size','opacity'])d[key]=item[key];if(item.type==='text')d.text=item.text;}
        this.sync();this.drawOverlay();return;
      }
      if(d.items.length>=500){this.pointerEnd(e,true);this.onError('This drawing is full. Remove an object to continue.');return;}
      const item={type:d.tool,x:p.x,y:p.y,sx:1,sy:1,rotation:0,size:d.size,color:d.color,fill:d.fill,filled:d.filled,opacity:d.opacity};
      if(FREE.has(d.tool))item.points=[[0,0,p.p]];
      else if(d.tool==='text'||d.tool==='sticker'){item.text=d.tool==='text'?(d.text||'Text'):d.sticker;item.h=d.tool==='text'?Math.max(24,d.size*5):128;item.w=d.tool==='text'?textWidth(item.text,item.h):128;}
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
      else if(drag.kind==='resize')resizeItem(d.items[this.selected],drag.item,drag.handle,p);
      else if(drag.kind==='rotate'){const angle=Math.atan2(p.y-drag.center.y,p.x-drag.center.x),degrees=drag.rotation+(angle-drag.angle)*180/Math.PI;Object.assign(d.items[this.selected],copy(drag.item));rotateItem(d.items[this.selected],degrees,drag.center);}
      else if(drag.kind==='draw'){
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
      const wasTouch=this.touches.delete(e.pointerId);
      if(this.pinch){if(this.touches.size<2)this.pinch=null;if(this.area.hasPointerCapture?.(e.pointerId))this.area.releasePointerCapture(e.pointerId);return;}
      const drag=this.drag;if(!drag||drag.id!==e.pointerId){if(wasTouch&&this.area.hasPointerCapture?.(e.pointerId))this.area.releasePointerCapture(e.pointerId);return;}this.drag=null;
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
    draw(){
      const source=referenceSource(this.doc);this.reference.hidden=!source;
      if(source&&this.reference.getAttribute('src')!==source)this.reference.src=source;
      if(!source)this.reference.removeAttribute('src');
      this.paper.style.backgroundColor=source?'transparent':this.doc.background;paint(this.canvas,this.doc,!source);this.drawOverlay();
    }
    drawOverlay(){
      this.overlay.width=this.doc.width;this.overlay.height=this.doc.height;
      const item=this.doc.items[this.selected];if(!item){this.layoutSelectionControls();return;}
      const c=this.overlay.getContext('2d'),frame=selectionFrame(item,this.zoom),unit=1/this.zoom;c.strokeStyle='#296ce8';c.lineWidth=1.5*unit;c.setLineDash([5*unit,3*unit]);c.beginPath();c.moveTo(frame.corners[0].x,frame.corners[0].y);frame.corners.slice(1).forEach(point=>c.lineTo(point.x,point.y));c.closePath();c.stroke();c.setLineDash([]);c.beginPath();c.moveTo(frame.points.n.x,frame.points.n.y);c.lineTo(frame.points.rotate.x,frame.points.rotate.y);c.stroke();this.layoutSelectionControls();
    }
    destroy(){
      if(this.editingText)this.finishTextEdit(false);
      if(this.drag)this.pointerEnd({pointerId:this.drag.id},true);this.destroyed=true;cancelAnimationFrame(this.frame);this.resizeObserver.disconnect();
      this.touches.clear();this.pinch=null;this.gesture=null;
      this.menus?.forEach(({menu,toggle})=>menu.removeEventListener('toggle',toggle));
      this.host.removeEventListener('click',this.click);this.host.removeEventListener('input',this.input);this.area.removeEventListener('wheel',this.wheel);
      this.area.removeEventListener('gesturestart',this.gestureStart);this.area.removeEventListener('gesturechange',this.gestureChange);this.area.removeEventListener('gestureend',this.gestureEnd);
      this.area.removeEventListener('dblclick',this.dblclick);this.inline.removeEventListener('keydown',this.inlineKey);this.inline.removeEventListener('input',this.inlineInput);this.inline.removeEventListener('blur',this.inlineBlur);
      for(const [type,fn] of [['pointerdown',this.down],['pointermove',this.move],['pointerup',this.up],['pointercancel',this.cancel],['lostpointercapture',this.cancel]])this.area.removeEventListener(type,fn);
      global.document.removeEventListener('keydown',this.key);global.document.removeEventListener('keyup',this.keyup);global.removeEventListener('blur',this.blur);
    }
  }
  global.SYLVEXSketch={create,restore,validSize,hasContent,documentSnapshot,commit,undo,localBounds,bounds,hit,textAt,textWidth,worldPoint,selectionFrame,resizeItem,rotateItem,drawItem,paint,referenceSource,exportPNG,Editor};
})(typeof window==='undefined'?globalThis:window);
