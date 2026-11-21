const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const {test} = require('node:test'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const file = process.env.GENERATION_CLIENT_SOURCE || [path.join(root,'webapp/js/cabinet.js'),path.join(root,'studio/js/website-studio.js')].find(file=>fs.existsSync(file));
const source = fs.readFileSync(file, 'utf8');
function declaration(name) {
  const start = new RegExp('^ *(?:async )?function '+name+'\\(', 'm').exec(source);
  assert(start, name);
  const tail = source.slice(start.index + start[0].length);
  const next = /^ *(?:async )?function [\w$]+\(/m.exec(tail);
  assert(next, name+' boundary');
  const chunk = source.slice(start.index, start.index + start[0].length + next.index);
  return chunk.slice(0, chunk.lastIndexOf('}')+1);
}
function harness(replies) {
  let calls = 0, clock = 0;
  const requests = [], states = [];
  const context = vm.createContext({Date:{now:()=>clock}, Promise, Map, Set, Error, DOMException,
    encodeURIComponent, activeGeneration:{jobId:'original'}, generationScopes:new Map(),
    updateSendButton:()=>{}, clearActiveProStudioJob:()=>{}, transitionActiveGeneration:()=>{},
    bindGenerationThought:()=>{}, noteGenerationJob:()=>{},
    translateGenerationError:(error,fallback)=>error.error||fallback,
    window:{dispatchEvent:()=>{}}, CustomEvent:class {},
    setTimeout:fn=>{clock+=600_000;queueMicrotask(fn)},clearTimeout:()=>{},
    fetch:async(url,request)=>{requests.push({url,request});return replies(++calls)},
  });
  vm.runInContext(declaration('isActiveGenerationStatus')+'\n'+declaration('waitGenerationJob')+'\n'+declaration('waitGridGeneration'),context);
  return {run:()=>context.waitGridGeneration('original',state=>states.push(state)), requests, states, calls:()=>calls};
}
const response = job => ({ok:true,status:200,json:async()=>({ok:true,...job})});
test('Normal and Grid keep the same job beyond every former waiting deadline',async()=>{
  const h=harness(call=>response(call<102?{status:'provider_processing'}:{status:'completed',result:{video_url:'synthetic'}}));
  const result=await h.run();assert.equal(result.job_id,'original');assert.equal(h.calls(),102);
  assert(h.requests.every(({request})=>!request.method));
  assert.equal(h.states.filter(x=>x==='provider_processing').length,101);
});
test('more than80 network failures retry status reads without resubmission',async()=>{
  const h=harness(call=>{if(call<102)throw Error('temporary network outage');return response({status:'completed',result:{text:'ready'}})});
  assert.equal((await h.run()).text,'ready');assert.equal(h.calls(),102);
  assert(h.requests.every(({request})=>!request.method));
});
test('confirmed failure stops the watcher and exposes its terminal state',async()=>{
  const h=harness(()=>response({status:'failed',error:{error:'confirmed failure'}}));
  await assert.rejects(h.run(),error=>error.terminalStatus==='failed');assert.equal(h.calls(),1);
});
test('processing stays on the fourth line until the result is ready',()=>{
  const context=vm.createContext({Number,Math,GENERATION_THOUGHT_ORDER:['received','sent','accepted','processing','ready']});
  vm.runInContext(declaration('generationThoughtTarget'),context);
  assert.equal(context.generationThoughtTarget({outcome:'working',stages:{received:1,sent:2,accepted:3,processing:4}}),3);
  assert.equal(context.generationThoughtTarget({outcome:'ready',stages:{}}),5);
});
test('video, music and voice uploads gate dispatch until they finish',()=>{
  const context=vm.createContext({imageState:{uploading:[]},videoState:{editUploading:{}},textState:{},
    isImageMode:()=>false,isVideoMode:()=>true,isMusicMode:()=>false,isVoiceMode:()=>false,currentAudioState:()=>({})});
  vm.runInContext(declaration('generationInputsUploading'),context);
  assert.equal(context.generationInputsUploading(),true);
  context.videoState.editUploading=null;context.videoState.referenceUploading={};assert.equal(context.generationInputsUploading(),true);
  context.videoState.referenceUploading=null;assert.equal(context.generationInputsUploading(),false);
  context.isVideoMode=()=>false;context.isVoiceMode=()=>true;context.currentAudioState=()=>({uploading:{}});assert.equal(context.generationInputsUploading(),true);
});
test('only the matching mode and model are locked; other workspaces remain usable',()=>{
  const context=vm.createContext({generationScopes:new Map([['video:kling:',{}]]),
    currentChatType:()=> 'video',pickStudioModel:()=> 'kling',chatTypeForMode:mode=>mode});
  vm.runInContext(declaration('generationScope')+'\n'+declaration('currentGenerationScope')+'\n'+declaration('activeGenerationLocked'),context);
  assert.equal(context.activeGenerationLocked(),true);context.pickStudioModel=()=> 'veo';assert.equal(context.activeGenerationLocked(),false);
  context.currentChatType=()=> 'image';assert.equal(context.activeGenerationLocked(),false);
});

function nodeContext(status) {
  const node={id:'n1',type:'image',settings:{},request_id:'stable-original-request',generation_id:'original-job',status};
  const state={projectId:'synthetic-project',nodes:[node],workflow:{}};
  const context=vm.createContext({Date,Promise,Map,JSON,studioGridNodeRuns:new Map(),studioGridJobsRestored:false,
    S:{user:{balance:100}},guestNeedsAccount:()=>false,loadStudioGridState:()=>state,
    resolveGridNodeInputs:()=>({}),validateGridNodeInputs:()=>({ok:true}),
    estimateGridNodeCost:async()=>5,ensureStudioGridProjectTitle:()=>{},saveStudioGridState:()=>{},
    renderStudioGrid:()=>{},toast:()=>{},translateGenerationError:e=>e.message});
  vm.runInContext(declaration('runGridNode')+'\n'+declaration('restoreStudioGridJobs'),context);
  return {node,context};
}
test('current node keeps request ID on unconfirmed wait; definitive failure still clears it',async()=>{
  for(const status of ['unconfirmed','failed']){
    const {node,context}=nodeContext('READY');
    const error=Object.assign(Error('synthetic status could not be confirmed'),{terminalStatus:status,jobId:'original-job'});
    context.executeGridNodeRequest=async()=>{throw error};
    await context.runGridNode('n1');
    assert.equal(node.generation_id,'original-job');
    assert.equal(node.request_id,status==='unconfirmed'?'stable-original-request':'');
  }
});
test('restored node keeps request ID on unconfirmed wait; definitive failure still clears it',async()=>{
  for(const status of ['unconfirmed','failed']){
    const {node,context}=nodeContext('RUNNING');
    const error=Object.assign(Error('synthetic status could not be confirmed'),{terminalStatus:status,jobId:'original-job'});
    context.waitGridGeneration=async()=>{throw error};
    context.restoreStudioGridJobs();await context.studioGridNodeRuns.get('n1');
    assert.equal(node.generation_id,'original-job');
    assert.equal(node.request_id,status==='unconfirmed'?'stable-original-request':'');
  }
});

test('concurrent status updates retain the original model and tool button scopes',()=>{
  const context=vm.createContext({Date,Map,Array,Object,String,
    activeGeneration:{jobId:'first',locked:true,mode:'video',model:'kling',scope:'video:kling:'},
    generationScopes:new Map([['video:kling:',{jobId:'first'}],['image:gpt:remove_object',{jobId:'second'}]]),
    currentChatType:()=> 'voice',pickStudioModel:()=> 'eleven',chatTypeForMode:mode=>mode,
    updateSendButton:()=>{},persistActiveGeneration:()=>{},document:{body:{classList:{remove:()=>{}}}}});
  vm.runInContext(declaration('isActiveGenerationStatus')+'\n'+declaration('generationScope')+'\n'+declaration('transitionActiveGeneration'),context);
  context.transitionActiveGeneration('status',{id:'second',mode:'image',status:'provider_processing'});
  assert.equal(context.generationScopes.size,2);
  assert.equal(context.generationScopes.get('image:gpt:remove_object').status,'provider_processing');
  assert.equal(context.generationScopes.has('image:eleven:'),false);
  context.transitionActiveGeneration('status',{id:'second',status:'failed'});
  assert.equal(context.generationScopes.size,1);assert(context.generationScopes.has('video:kling:'));
});

test('closing an active photo tool preserves its task and permits navigation',()=>{
  const hidden=[], navigation=[];
  const state={generating:true,files:['source']};
  const modal={classList:{remove:name=>hidden.push(name)}};
  const context=vm.createContext({activePhotoTool:'remove_object',photoToolState:{remove_object:state},
    photoToolReturnMode:'video',studioMode:'image',document:{getElementById:()=>modal},
    window:{SYLVEX:{browserNav:{closed:key=>navigation.push(key)}}},updateComposerMode:mode=>navigation.push(mode)});
  vm.runInContext(declaration('closePhotoToolModal'),context);
  context.closePhotoToolModal();assert.deepEqual(hidden,['show']);assert.equal(state.generating,true);
  assert.deepEqual(state.files,['source']);assert(navigation.includes('video'));
});
test('a Grid node finishes in its original project after switching projects',async()=>{
  const {node,context}=nodeContext('READY');
  const original=context.loadStudioGridState(),other={projectId:'other',nodes:[],workflow:{}};
  let begin,finish;const dispatched=new Promise(resolve=>begin=resolve),saved=[];
  context.executeGridNodeRequest=async(n,inputs,onJob,state)=>{assert.equal(state,original);onJob('original-job');begin();return await new Promise(resolve=>finish=resolve)};
  context.normalizeGridNodeResult=()=>({type:'image',items:[],generation_id:'original-job'});
  context.markStudioGridDownstreamStale=(id,state)=>assert.equal(state,original);
  context.saveStudioGridState=state=>saved.push(state);
  const running=context.runGridNode('n1');await dispatched;context.loadStudioGridState=()=>other;
  finish({generation_id:'original-job'});await running;
  assert.equal(node.status,'COMPLETED');assert.equal(context.loadStudioGridState(),other);
  assert.equal(saved.at(-1),original);
});
test('saving a detached Grid result updates its project without replacing the active project',()=>{
  const active={projectId:'active'},original={projectId:'original'},writes=[],cloud=[];
  const context=vm.createContext({studioGridState:active,JSON,
    ensureStudioGridStorageOwner:()=>{},touchStudioGridProject:()=>true,
    studioGridActiveStorageKey:()=> 'active-key',studioGridProjectStorageKey:id=>'project:'+id,
    localStorage:{setItem:(key,value)=>writes.push(key)},scheduleStudioGridCloudSave:()=>assert.fail('active project must stay unchanged'),
    queueStudioGridCloudSave:state=>cloud.push(state)});
  vm.runInContext(declaration('saveStudioGridState'),context);context.saveStudioGridState(original);
  assert.deepEqual(writes,['project:original']);assert.equal(cloud[0],original);assert.equal(context.studioGridState,active);
});
