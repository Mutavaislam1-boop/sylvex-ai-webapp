import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import vm from 'node:vm';

const path = existsSync(new URL('../webapp/js/cabinet.js', import.meta.url))
  ? '../webapp/js/cabinet.js' : '../studio/js/website-studio.js';
const source = readFileSync(new URL(path, import.meta.url), 'utf8');
function fn(name) {
  const match = new RegExp('^[ \\t]*(?:async )?function ' + name + '\\(', 'm').exec(source);
  assert.ok(match, name + ' exists');
  let depth = 0;
  for (let i = source.indexOf('{', match.index); i < source.length; i++) {
    if (source[i] === '{') depth++;
    if (source[i] === '}' && --depth === 0) return source.slice(match.index, i + 1);
  }
  assert.fail('Unclosed function: ' + name);
}
const escapeHtml = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll("'",'&#39;');
const images = Array.from({length:4}, (_, i) => ({url:'https://media.example.test/'+i+'.jpg',thumb:'https://media.example.test/'+i+'-thumb.jpg'}));
function harness(extra={}) {
  let owner = 7;
  const calls = {downloads:[],fetch:[],timers:[],revoked:[],toasts:[]};
  class TestURL extends URL {
    static createObjectURL(){return 'blob:test-image';}
    static revokeObjectURL(value){calls.revoked.push(value);}
  }
  const ctx = vm.createContext({URL:TestURL,URLSearchParams,
    window:{location:{origin:'https://website.example.test'},innerWidth:1200,innerHeight:800,
      setTimeout:fn=>{calls.timers.push(fn);return calls.timers.length;},clearTimeout(){}},
    S:{escapeHtml,tg:null},getTelegramId:()=>owner,generationActionIcon:()=>'',
    renderCompletedGenerationDownload:()=> 'legacy-single',
    fetchWithTimeout:async(url,options)=>{calls.fetch.push({url,options});return {ok:true,blob:async()=>({size:10,type:'image/jpeg'})};},
    browserDownload:(url,name)=>calls.downloads.push({url,name}),toast:text=>calls.toasts.push(text),
    ...extra});
  function load(...names){vm.runInContext(names.map(fn).join('\n'),ctx);return ctx;}
  return {ctx,calls,load,setOwner:value=>{owner=value;}};
}
function state(selected=[0,2]) {
  return {jobId:'owned-job',images,owner:'7',projectId:'',nodeId:'',selected:new Set(selected),busy:false,completed:0,total:0,message:''};
}

test('a multi-image card opens a chooser; a single result keeps the working direct download', () => {
  const h=harness();h.load('renderGenerationImageDownloadTrigger');
  const html=h.ctx.renderGenerationImageDownloadTrigger('owned-job','completed',images);
  assert.match(html,/openGenerationImageDownloadPicker\(event\)/);
  assert.match(html,/data-download-images=/);
  assert.doesNotMatch(html,/download_all|\.zip/);
  assert.equal(h.ctx.renderGenerationImageDownloadTrigger('owned-job','completed',images.slice(0,1)),'legacy-single');
  assert.equal(h.ctx.renderGenerationImageDownloadTrigger('owned-job','running',images),'');
});

test('the chooser renders every photo and explicit selected state, including sets larger than four', () => {
  const h=harness();h.load('renderGenerationImageDownloadPicker');
  const picker={_generationDownloadState:{...state([]),images:[...images,...images]}};
  h.ctx.renderGenerationImageDownloadPicker(picker);
  assert.equal((picker.innerHTML.match(/data-generation-image-index=/g)||[]).length,8);
  assert.match(picker.innerHTML,/data-generation-picker-download disabled/);
  picker._generationDownloadState.selected=new Set([1,4]);
  h.ctx.renderGenerationImageDownloadPicker(picker);
  assert.equal((picker.innerHTML.match(/aria-pressed="true"/g)||[]).length,2);
  assert.match(picker.innerHTML,/\(2\)/);
  assert.doesNotMatch(picker.innerHTML,/\.zip|download_all/);
});

test('one, several and all selected photos start separate sequential downloads without duplicate clicks', async () => {
  for (const selection of [[2],[0,2],[0,1,2,3]]) {
    const seen=[];let active=0,maxActive=0;
    const h=harness({renderGenerationImageDownloadPicker(){},downloadOneGenerationImage:async(_state,index)=>{
      active++;maxActive=Math.max(active,maxActive);seen.push(index);await Promise.resolve();active--;
    }});
    h.load('downloadGenerationImageSelection');
    const picker={_generationDownloadState:state(selection),hidden:false};
    await Promise.all([h.ctx.downloadGenerationImageSelection(picker),h.ctx.downloadGenerationImageSelection(picker)]);
    assert.deepEqual(seen,selection);
    assert.equal(maxActive,1);
    assert.equal(picker._generationDownloadState.selected.size,0);
    assert.equal(picker._generationDownloadState.busy,false);
    assert.equal(picker.hidden,true);
  }
});

test('an interrupted batch retains only unfinished choices; retry does not download earlier files again', async () => {
  const seen=[];
  const h=harness({renderGenerationImageDownloadPicker(){},downloadOneGenerationImage:async(_state,index)=>{
    seen.push(index);if(index===1)throw new Error('test interruption');
  }});
  h.load('downloadGenerationImageSelection');
  const picker={_generationDownloadState:state([0,1,2]),hidden:false};
  await h.ctx.downloadGenerationImageSelection(picker);
  assert.deepEqual(seen,[0,1]);
  assert.deepEqual([...picker._generationDownloadState.selected],[1,2]);
  assert.equal(picker._generationDownloadState.busy,false);
  assert.equal(picker.hidden,false);
  h.ctx.downloadOneGenerationImage=async(_state,index)=>seen.push(index);
  await h.ctx.downloadGenerationImageSelection(picker);
  assert.deepEqual(seen,[0,1,1,2]);
});

test('browser files use the authenticated single-image stream and distinct correct filenames', async () => {
  const h=harness();h.load('completedGenerationDownloadUrl','generationImageDownloadName','downloadOneGenerationImage');
  await h.ctx.downloadOneGenerationImage(state(),2);
  const request=new URL(h.calls.fetch[0].url);
  assert.equal(request.searchParams.get('stream_image'),'true');
  assert.equal(request.searchParams.get('result_index'),'2');
  assert.equal(request.searchParams.has('download_all'),false);
  assert.equal(h.calls.fetch[0].options.credentials,'include');
  assert.equal(h.calls.downloads[0].name,'sylvex-image-owned-job-3.jpg');
  assert.equal(h.ctx.generationImageDownloadName('owned-job',0,'image/png',images[0].url),'sylvex-image-owned-job-1.png');
  h.calls.timers.forEach(fn=>fn());
  assert.deepEqual(h.calls.revoked,['blob:test-image']);
});

test('HTTP errors and an identity change never save an error page or a previous account file', async () => {
  const failed=harness({fetchWithTimeout:async()=>({ok:false})});
  failed.load('completedGenerationDownloadUrl','generationImageDownloadName','downloadOneGenerationImage');
  await assert.rejects(failed.ctx.downloadOneGenerationImage(state(),0));
  assert.equal(failed.calls.downloads.length,0);
  const changed=harness();
  changed.ctx.fetchWithTimeout=async()=>({ok:true,blob:async()=>{changed.setOwner(8);return {size:10,type:'image/jpeg'};}});
  changed.load('completedGenerationDownloadUrl','generationImageDownloadName','downloadOneGenerationImage');
  await assert.rejects(changed.ctx.downloadOneGenerationImage(state(),0));
  assert.equal(changed.calls.downloads.length,0);
});

test('Grid uses the same chooser while preserving the project, node and complete result list', async () => {
  const calls=[],node={id:'node-four',generation_id:'owned-job',output:{type:'image',items:images}};
  const anchor={};
  const h=harness({loadStudioGridState:()=>({projectId:'project-7',nodes:[node]}),
    openGenerationImageDownloadPicker:(event,context)=>calls.push(context),triggerStudioGridDownload:()=>assert.fail('multi-image Grid must open the chooser')});
  h.load('downloadStudioGridNode');h.ctx.downloadStudioGridNode(node.id,anchor);
  assert.equal(calls.length,1);assert.equal(calls[0].images.length,4);
  assert.equal(calls[0].jobId,'owned-job');assert.equal(calls[0].projectId,'project-7');assert.equal(calls[0].nodeId,node.id);
  h.load('completedGenerationDownloadUrl','completedGridDownloadUrl','generationImageDownloadName','downloadOneGenerationImage');
  await h.ctx.downloadOneGenerationImage({...state(),projectId:'project-7',nodeId:'node-four'},3);
  const url=new URL(h.calls.fetch[0].url);
  assert.equal(url.searchParams.get('grid_project_id'),'project-7');assert.equal(url.searchParams.get('grid_node_id'),'node-four');
  assert.equal(url.searchParams.get('result_index'),'3');assert.equal(url.searchParams.get('stream_image'),'true');
});

test('real Telegram initialization retains the native download mechanism and never falls back after a decline', async () => {
  const native=[];
  const h=harness({S:{escapeHtml,tg:{initData:'dummy-init-data',downloadFile:(options,done)=>{native.push(options);done(true);}}}});
  h.load('completedGenerationDownloadUrl','generationImageDownloadName','downloadOneGenerationImage');
  await h.ctx.downloadOneGenerationImage(state(),1);
  assert.equal(native.length,1);assert.equal(h.calls.fetch.length,0);
  assert.equal(new URL(native[0].url).searchParams.get('result_index'),'1');
  assert.equal(native[0].file_name,'sylvex-image-owned-job-2.jpg');
  h.ctx.S.tg.downloadFile=(_options,done)=>done(false);
  await assert.rejects(h.ctx.downloadOneGenerationImage(state(),2));
  assert.equal(h.calls.fetch.length,0);
});
