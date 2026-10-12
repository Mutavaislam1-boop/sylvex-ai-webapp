import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const context=vm.createContext({console});
vm.runInContext(readFileSync(new URL('../webapp/js/edit-sketch.js',import.meta.url),'utf8'),context);
const sketch=context.SYLVEXSketch;
const stroke=()=>({type:'pen',x:40,y:50,sx:1,sy:1,rotation:0,size:6,color:'#123456',fill:'#ffffff',opacity:1,points:[[0,0,.5],[100,80,.8]]});
test('drawing undo/redo restores ordered strokes, erasers, clear and canvas dimensions',()=>{
 const d=sketch.create();let before=sketch.documentSnapshot(d);d.items.push(stroke());sketch.commit(d,before);
 before=sketch.documentSnapshot(d);d.items.push({...stroke(),type:'eraser'});sketch.commit(d,before);
 before=sketch.documentSnapshot(d);d.items=[];d.width=2048;sketch.commit(d,before);
 assert.equal(sketch.undo(d),true);assert.equal(d.items.length,2);assert.equal(d.width,1024);
 assert.equal(sketch.undo(d),true);assert.equal(d.items[0].type,'pen');assert.equal(d.items.length,1);
 assert.equal(sketch.undo(d,true),true);assert.equal(d.items[1].type,'eraser');
 before=sketch.documentSnapshot(d);d.background='#abc123';sketch.commit(d,before);assert.equal(sketch.undo(d,true),false);
});
test('history limits roll back an oversized addition without losing the previous drawing',()=>{
 const d=sketch.create();d.items=[stroke()];const before=sketch.documentSnapshot(d);d.items=Array.from({length:501},stroke);
 assert.throws(()=>sketch.commit(d,before),/drawing is full/);assert.equal(d.items.length,1);
});
test('selection bounds follow negative-direction lines, resized objects and rotation',()=>{
 const item={...stroke(),type:'arrow',points:undefined,w:-100,h:-80};
 assert.equal(sketch.hit(item,{x:-20,y:10}),true);assert.equal(sketch.hit(item,{x:1000,y:1000}),false);
 assert.equal(sketch.bounds(item).x,-63);item.sx=2;item.sy=2;assert.equal(sketch.bounds(item).w,212);
 item.rotation=90;const b=sketch.bounds(item);assert.ok(Math.abs(b.h-212)<.001);
});
test('all eight selection handles resize from their own edge and keep the opposite anchor fixed',()=>{
 const original={type:'rectangle',x:100,y:80,w:120,h:60,sx:1,sy:1,rotation:27,size:2,color:'#123456',fill:'#ffffff',opacity:1};
 const opposite={e:'w',w:'e',s:'n',n:'s',se:'nw',sw:'ne',ne:'sw',nw:'se'};
 for(const [handle,anchor] of Object.entries(opposite)){
   const item={...original},frame=sketch.selectionFrame(item),before=frame.points[anchor],b=sketch.localBounds(item),local={nw:[b.x,b.y],n:[b.x+b.w/2,b.y],ne:[b.x+b.w,b.y],e:[b.x+b.w,b.y+b.h/2],se:[b.x+b.w,b.y+b.h],s:[b.x+b.w/2,b.y+b.h],sw:[b.x,b.y+b.h],w:[b.x,b.y+b.h/2]},start=local[handle],fixed=local[anchor],a=original.rotation*Math.PI/180;
   const dx=(start[0]-fixed[0])*(handle.includes('e')||handle.includes('w')?1.5:1),dy=(start[1]-fixed[1])*(handle.includes('n')||handle.includes('s')?2:1),pointer={x:before.x+dx*Math.cos(a)-dy*Math.sin(a),y:before.y+dx*Math.sin(a)+dy*Math.cos(a)};
   sketch.resizeItem(item,{...original},handle,pointer);const after=sketch.selectionFrame(item).points[anchor];
   assert.ok(Math.abs(before.x-after.x)<.001,handle+' keeps x anchor');assert.ok(Math.abs(before.y-after.y)<.001,handle+' keeps y anchor');
   if(handle.includes('e')||handle.includes('w'))assert.ok(Math.abs(item.sx-1.5)<.001);if(handle.includes('n')||handle.includes('s'))assert.ok(Math.abs(item.sy-2)<.001);
 }
});
test('free rotation is normalized to 360 degrees and preserves the visual center',()=>{
 const item={type:'rectangle',x:100,y:80,w:120,h:60,sx:1.4,sy:.8,rotation:25,size:2,color:'#123456',fill:'#ffffff',opacity:1};
 const center=sketch.selectionFrame(item).center;sketch.rotateItem(item,405);const after=sketch.selectionFrame(item).center;
 assert.equal(item.rotation,45);assert.ok(Math.abs(center.x-after.x)<.001);assert.ok(Math.abs(center.y-after.y)<.001);
 const frame=sketch.selectionFrame(item,2);assert.ok(frame.points.rotate&&frame.corners.length===4);
});
test('text tool recognizes a second click on text and expands the editor width with input',()=>{
 const d=sketch.create(),text=(value,x=100)=>({type:'text',text:value,x,y:80,w:sketch.textWidth(value,30),h:30,sx:1,sy:1,rotation:0,size:4,color:'#202534',fill:'#ffffff',opacity:1});
 d.items=[text('First'),text('Top')];
 assert.equal(sketch.textAt(d,{x:115,y:90}),1,'the top text object is edited instead of inserting another one');
 assert.equal(sketch.textAt(d,{x:500,y:500}),-1,'a free position remains available for a new text object');
 assert.ok(sketch.textWidth('A much longer line',30)>sketch.textWidth('Text',30));
});
test('restoration keeps editable artwork and rejects corrupt canvas geometry and unsafe colors',()=>{
 const d=sketch.create();d.items=[stroke(),{...stroke(),type:'arrow',points:undefined,w:-40,h:-20}];
 const saved=JSON.parse(JSON.stringify(d));assert.equal(sketch.restore(saved).items.length,2);assert.equal(sketch.hasContent(sketch.restore(saved)),true);
 saved.items[0].color='url(javascript:bad)';assert.equal(sketch.restore(saved).items.length,1);
 saved.width=100000;assert.equal(sketch.restore(saved).width,1024);assert.equal(sketch.restore(saved).items.length,0);
 assert.equal(sketch.hasContent({...d,items:[{...stroke(),type:'eraser'}]}),false);
});
test('drawing renderer applies erasing only to its layer and restores compositing for later objects',()=>{
 const events=[],ctx=new Proxy({},{get:(target,key)=>target[key]??((...args)=>events.push([key,...args])),set:(target,key,v)=>{events.push([key,v]);target[key]=v;return true;}});
 sketch.drawItem(ctx,{...stroke(),type:'eraser'});sketch.drawItem(ctx,stroke());
 assert.ok(events.some(([k,v])=>k==='globalCompositeOperation'&&v==='destination-out'));
 assert.equal(events.filter(([k])=>k==='save').length,2);assert.equal(events.filter(([k])=>k==='restore').length,2);
});
test('expanded shape library remains editable and renders every added shape',()=>{
 const events=[],ctx=new Proxy({},{get:(target,key)=>target[key]??((...args)=>events.push([key,...args])),set:(target,key,v)=>{target[key]=v;return true;}}),types=['diamond','pentagon','hexagon','cross','speech'];
 const d=sketch.create();d.items=types.map((type,index)=>({type,x:index*120,y:40,w:96,h:72,sx:1,sy:1,rotation:0,size:4,color:'#202534',fill:'#a7c7f2',filled:true,opacity:1}));
 types.forEach((type,index)=>sketch.drawItem(ctx,d.items[index]));
 assert.equal(sketch.restore(JSON.parse(JSON.stringify(d))).items.length,types.length);
 assert.equal(events.filter(([key])=>key==='stroke').length,types.length);
});
