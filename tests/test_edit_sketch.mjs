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
