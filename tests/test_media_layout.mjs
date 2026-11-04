import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync,existsSync} from 'node:fs';
const root=new URL('../',import.meta.url),mini=existsSync(new URL('webapp/js/media-page.js',root));
const source=readFileSync(new URL(mini?'webapp/js/media-page.js':'js/media-page.js',root),'utf8');
const html=readFileSync(new URL(mini?'webapp/cabinet.html':'media.html',root),'utf8');
function fn(name){const i=source.indexOf('  function '+name+'(');assert.ok(i>=0);const end=source.indexOf('\n  function ',i+1);return source.slice(i,end<0?undefined:end);}
function fixture(width){
 const columns=[];let observer;
 const wall={clientWidth:width,dataset:{},classList:{remove(){}},querySelectorAll:()=>columns};
 Object.defineProperty(wall,'innerHTML',{set(value){columns.length=0;for(const _ of value.matchAll(/sx-media-col/g)){const col={children:[],appendChild(card){this.children.push(card);}};Object.defineProperty(col,'offsetHeight',{get:()=>wall.clientWidth?col.children.length*100:0});columns.push(col);}}});
 const nodes={sxMediaWall:wall,sxMediaWallEmpty:{},sxMediaMore:{}};
 class ResizeObserver{constructor(callback){observer=callback;}observe(value){assert.equal(value,wall);}}
 const context=vm.createContext({window:{innerWidth:1400,ResizeObserver,addEventListener(){}},ResizeObserver,document:{createElement(){return{set innerHTML(id){this.firstChild={id};}};}},$:id=>nodes[id],MEDIA:{interleave:x=>x},state:{items:Array.from({length:12},(_,i)=>({id:'card-'+i,kind:'image'}))},wallKind:'all',BATCH:36,wallList:[],wallNeedsLayout:false,shown:0,moreObserver:null,cardHtml:x=>x.id,fitImage(){},prepareReveal(){},observeVideos(){},clearTimeout(){},setTimeout(){}});
 for(const name of ['columnCount','renderWall','appendBatch','refreshWallLayout'])vm.runInContext(fn(name),context);
 return {context,wall,columns,resize:()=>observer()};
}
test('hidden Mini Media lays out all cards after becoming visible, even at the same column count',()=>{
 const f=fixture(0);f.context.window.innerWidth=390;f.context.renderWall();assert.equal(f.columns.length,0);
 f.wall.clientWidth=360;f.resize();assert.equal(f.columns.length,2);assert.deepEqual(f.columns.map(x=>x.children.length),[6,6]);
});
test('a wide browser uses the Mini container width; hiding cannot append or duplicate cards',()=>{
 const f=fixture(448);f.context.renderWall();assert.equal(f.columns.length,2);
 f.wall.clientWidth=0;f.context.appendBatch();assert.equal(f.context.shown,12);
 f.wall.clientWidth=448;f.resize();const ids=f.columns.flatMap(x=>x.children.map(c=>c.id));assert.equal(ids.length,12);assert.equal(new Set(ids).size,12);
 f.resize();assert.equal(f.columns.flatMap(x=>x.children).length,12);
});
test('Media contains only the catalog without requested-to-remove chrome; missing Featured is safe',()=>{
 const section=mini?html.slice(html.indexOf('data-view="media"'),html.indexOf('<dialog class="sx-media-viewer"')):html;
 assert.doesNotMatch(section,/<h1>Media|Every visual catalog|sxMediaFeatured|data-media-kind|Featured references/);
 assert.match(section,/id="sxMediaWall"/);
 const c=vm.createContext({$:()=>null,state:{featured:[{id:'item'}]}});vm.runInContext(fn('renderFeatured'),c);assert.doesNotThrow(()=>c.renderFeatured());
});
