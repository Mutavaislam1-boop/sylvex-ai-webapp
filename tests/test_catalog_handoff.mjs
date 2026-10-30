import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync,existsSync} from 'node:fs';

const root=new URL('../',import.meta.url);
const controller=existsSync(new URL('studio/js/website-studio.js',root))?'studio/js/website-studio.js':'webapp/js/cabinet.js';
const source=readFileSync(new URL(controller,root),'utf8');
function fn(name){
  const start=source.search(new RegExp('(?:async )?function '+name+'\\('));
  assert.ok(start>=0,name);
  const tail=source.slice(start), next=tail.slice(1).search(/\n(?:  )?(?:async )?function /);
  return next<0?tail:tail.slice(0,next+1);
}
function context(extra={}){
  const c=vm.createContext({console,Date,Set,Map,Number,URLSearchParams,encodeURIComponent,window:{},currentVideoReferenceImages:()=>[],setCurrentVideoReferenceImages:()=>{},S:{whenProStudioReady:async()=>{}},...extra});
  return c;
}

test('video handoff applies source/settings to composer without opening a modal or posting a job',async()=>{
  const c=context({setUploadTarget:()=>{},UPLOAD_TARGETS:{VIDEO_START:'start'},videoState:{startImage:'keep-photo',referenceImageUrls:['keep-ref']},
    switchView:()=>{},closeVideoTemplatesCatalog:()=>{},closePhotoCatalog:()=>{},updateComposerMode:()=>{},
    loadVideoTemplates:async()=>[],mediaVideoTemplate:()=>({id:'04',resolution:'720p',reference_video:'https://cdn.test/source.mp4'}),
    videoTemplateReferenceVideo:t=>t.reference_video,templatePreferredModel:()=> 'kling_motion_3_0',
    normalizeVideoStateForModel:()=>{},renderVideoControls:()=>{},renderUploadedPhotoGrid:()=>{},
    saveComposerDraftIfChanged:()=>{},updateSendButton:()=>{},fetch:()=>{throw new Error('No job may be submitted');}});
  vm.runInContext(fn('restoreMediaAcceptedJob'),c);
  vm.runInContext(fn('openMediaHandoff'),c);
  assert.equal(await c.openMediaHandoff({kind:'video_template',itemId:'04',resolution:'1080p'}),true);
  assert.equal(c.videoState.editInputVideo,'https://cdn.test/source.mp4');
  assert.equal(c.videoState.startImage,'keep-photo');
  assert.deepEqual(Array.from(c.videoState.referenceImageUrls),['keep-ref']);
  assert.equal(c.videoState.resolution,'1080p');
  assert.equal(c.videoState.videoTemplate.catalog_type,'video_template');
});

test('image reuse merges existing references and never calls generation',async()=>{
  let refs;
  const c=context({switchView:()=>{},closeVideoTemplatesCatalog:()=>{},closePhotoCatalog:()=>{},updateComposerMode:()=>{},
    currentUploadImages:()=>['existing'],setCurrentUploadImages:r=>{refs=r;},UPLOAD_TARGETS:{IMAGE_UPLOAD:'image'},
    saveComposerDraftIfChanged:()=>{},updateSendButton:()=>{}});
  vm.runInContext(fn('restoreMediaAcceptedJob'),c);
  vm.runInContext(fn('openMediaHandoff'),c);
  await c.openMediaHandoff({kind:'image_reference',resultUrl:'ready-image'});
  assert.deepEqual(Array.from(refs),['existing','ready-image']);
});

test('style handoff preserves customization without forwarding a style thumbnail as an identity image',async()=>{
  let refs;
  const c=context({switchView:()=>{},closeVideoTemplatesCatalog:()=>{},closePhotoCatalog:()=>{},updateComposerMode:()=>{},imageState:{},
    currentUploadImages:()=>['existing'],setCurrentUploadImages:r=>{refs=r;},UPLOAD_TARGETS:{IMAGE_UPLOAD:'image'},
    mediaImageItem:async()=>({item:{id:'photo_09',kind:'styles',prompt:'Apply the catalog style',url:'style-thumbnail'}}),renderImageControls:()=>{},
    saveComposerDraftIfChanged:()=>{},updateSendButton:()=>{},pendingCatalogImageGeneration:null});
  vm.runInContext(fn('restoreMediaAcceptedJob'),c);vm.runInContext(fn('openMediaHandoff'),c);
  await c.openMediaHandoff({kind:'image',itemId:'photo_09',image:'style-thumbnail',upload:'user-photo',fields:{name:'Example'}});
  assert.deepEqual(Array.from(refs),['existing','user-photo']);assert.equal(c.imageState.style,'photo_09');
  assert.match(c.pendingCatalogImageGeneration.prompt,/name: Example/);assert.equal(c.imageState.modelId,'gpt_image_2');
});

test('Kling Effects handoff remains an effect and never becomes character replacement',async()=>{
  const effect={id:'hug',catalog_type:'kling_effect',is_kling_effect:true,effect_scene:'hug'};
  const c=context({videoState:{},switchView:()=>{},closeVideoTemplatesCatalog:()=>{},closePhotoCatalog:()=>{},updateComposerMode:()=>{},
    loadKlingEffects:async()=>[effect],mediaVideoTemplate:()=>effect,videoTemplateReferenceVideo:()=>'',
    setUploadTarget:()=>{},UPLOAD_TARGETS:{VIDEO_START:'start'},normalizeVideoStateForModel:()=>{},renderVideoControls:()=>{},renderUploadedPhotoGrid:()=>{},saveComposerDraftIfChanged:()=>{},updateSendButton:()=>{}});
  vm.runInContext(fn('restoreMediaAcceptedJob'),c);vm.runInContext(fn('openMediaHandoff'),c);
  await c.openMediaHandoff({kind:'video_effect',itemId:'hug',upload:'photo'});
  assert.equal(c.videoState.modelId,'kling_effects');assert.equal(c.videoState.editInputVideo,'');
  assert.equal(c.videoState.videoTemplate.catalog_type,'kling_effect');assert.equal(c.videoState.startImage,'photo');
});

test('restored video metadata names the job model rather than the current composer model',()=>{
  const c=context({generatedUrlsFromResponse:()=>['ready-video'],videoState:{modelId:'seedance_2_fast'},pickStudioModel:()=> 'seedance_2_fast',
    VIDEO_MODELS:[{id:'kling_motion_3_0',label:'Kling 3.0 Omni'}]});
  vm.runInContext(fn('generationResultMetadata'),c);
  const meta=c.generationResultMetadata('video','replace',{type:'video',model:'kling_motion_3_0',provider:'kling',job_id:'original'},[],null);
  assert.equal(meta.model,'kling_motion_3_0');assert.equal(meta.model_label,'Kling 3.0 Omni');assert.equal(meta.job_id,'original');
});

test('handoff waits for account and draft synchronization instead of being overwritten by it',async()=>{
  let ready,switched=0;
  const waiting=new Promise(resolve=>{ready=resolve;});
  const c=context({S:{whenProStudioReady:()=>waiting},switchView:()=>{switched++;},closeVideoTemplatesCatalog:()=>{},closePhotoCatalog:()=>{},updateComposerMode:()=>{},
    currentUploadImages:()=>[],setCurrentUploadImages:()=>{},UPLOAD_TARGETS:{IMAGE_UPLOAD:'image'},saveComposerDraftIfChanged:()=>{},updateSendButton:()=>{}});
  vm.runInContext(fn('restoreMediaAcceptedJob'),c);
  vm.runInContext(fn('openMediaHandoff'),c);
  const handoff=c.openMediaHandoff({kind:'image_reference',resultUrl:'ready-image'});
  assert.equal(switched,0);ready();await handoff;assert.equal(switched,1);
});

test('an accepted job is restored only by GET and uses its original id',async()=>{
  const calls=[],watched=[];
  const c=context({switchView:()=>{},closeVideoTemplatesCatalog:()=>{},closePhotoCatalog:()=>{},updateComposerMode:()=>{},
    fetch:async(url,options)=>{calls.push([url,options]);return {ok:true,json:async()=>({ok:true,status:'processing'})};},
    loadVideoTemplates:async()=>[],mediaVideoTemplate:()=>null,saveComposerDraftIfChanged:()=>{},updateSendButton:()=>{},isActiveGenerationStatus:s=>s==='processing',applyActiveProStudioJob:()=>{},ensureActiveGenerationPlaceholder:()=>{},
    watchGenerationJob:(id,info)=>watched.push([id,info])});
  vm.runInContext(fn('restoreMediaAcceptedJob'),c);
  vm.runInContext(fn('openMediaHandoff'),c);
  await c.openMediaHandoff({kind:'video_template',jobId:'same-job-1'});
  assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/public/prostudio/job/same-job-1');
  assert.equal(calls[0][1].method,undefined);assert.equal(watched[0][0],'same-job-1');
});

test('finished event is delivered once per job and authenticated account',()=>{
  const events=[];let owner='account-a';
  const c=context({deliveredGenerationJobs:new Map(),localAccountStorageOwner:()=>owner,
    CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},window:{dispatchEvent:e=>events.push(e)}});
  vm.runInContext(fn('emitGenerationResultOnce'),c);
  c.emitGenerationResultOnce({job_id:'one'});c.emitGenerationResultOnce({job_id:'one'});
  assert.equal(events.length,1);owner='account-b';c.emitGenerationResultOnce({job_id:'one'});assert.equal(events.length,2);
});

test('restoration adopts one pending row per job and disposes duplicate timers',()=>{
  let disposed=0;
  const c=context({
    activeGeneration:{locked:true,jobId:'job-one',loadingToken:'new-window-token',mode:'video',status:'processing'},
    chatMessages:[{role:'user',text:'source'},{role:'ai',generationLoading:true,thoughtKey:'stale',activeGenerationToken:'old-a'},
      {role:'ai',generationLoading:true,thoughtKey:'restored',generationJobId:'job-one',activeGenerationToken:'old-b'}],
    generationThoughtLines:new Map([['stale',{handle:{unmount(){disposed++;}}}]]),
    chatThoughtTracks:new Map(),generationThoughtJobs:new Map(),clearTimeout:()=>{},
    generationLoadingThought:()=>({thoughtKey:'new-thought',thought:{}}),generationKindForCurrentMode:()=> 'video',renderChat:()=>{},
  });
  for(const name of ['activeGenerationPlaceholderIndex','disposeGenerationPlaceholder','adoptActiveGenerationPlaceholder','ensureActiveGenerationPlaceholder'])vm.runInContext(fn(name),c);
  const first=c.ensureActiveGenerationPlaceholder(false);
  assert.equal(first,1);assert.equal(c.chatMessages.length,2);assert.equal(c.chatMessages[1].generationJobId,'job-one');
  assert.equal(c.chatMessages[1].activeGenerationToken,'new-window-token');assert.equal(disposed,1);
  assert.equal(c.ensureActiveGenerationPlaceholder(false),1);assert.equal(c.chatMessages.length,2);
});

test('provider ready timestamp cannot finish a job still saving the result',()=>{
  const seen=[];
  const c=context({generationThoughtJobs:new Map([['j',new Map([['t',{}]])]]),
    applyGenerationThoughtProgress:(thought,progress)=>seen.push(progress),showGenerationThought:()=>{},finishGenerationThought:()=>{}});
  vm.runInContext(fn('noteGenerationJob'),c);
  c.noteGenerationJob('j',{status:'processing',progress:{stages:{received:1,ready:2}}});
  assert.equal(seen[0].stages.ready,undefined);assert.equal(seen[0].stages.received,1);
  assert.equal(c.generationThoughtJobs.has('j'),true);
});

test('catalog edit uses Omni input limits while standalone Motion retains image-orientation limits',()=>{
  const c=context({isVideoMode:()=>true,videoState:{modelId:'kling_motion_3_0',section:'edit',videoTemplate:{catalog_type:'video_template'}},
    fetchedModelCapabilities:{models:{kling_motion_3_0:{reference_inputs:{accepts_video:true,video_min_seconds:3,video_max_seconds:30,video_max_seconds_by_orientation:{image:10}}},kling_o3_omni:{reference_inputs:{accepts_video:true,video_min_seconds:3,video_max_seconds:15.5}}}}});
  vm.runInContext(fn('currentReferenceVideoLimits'),c);
  assert.equal(c.currentReferenceVideoLimits().video_max_seconds,15.5);
  c.videoState.section='motion';c.videoState.videoTemplate=null;
  assert.equal(c.currentReferenceVideoLimits().video_max_seconds,10);
});
