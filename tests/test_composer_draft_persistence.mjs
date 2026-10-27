import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source=readFileSync(new URL('../webapp/js/cabinet.js',import.meta.url),'utf8');
const a=source.indexOf('  const composerDraftInitialStates'),b=source.indexOf('  async function saveVisualItemToBackend(',a);
const clone=value=>JSON.parse(JSON.stringify(value));
const image=()=>({modelId:'image-a',size:'1:1',count:1,style:'auto',seed:null,uploadedImageUrls:[],referenceImageUrls:[],referenceImageUrl:'',characterReferences:[],objectReferences:[],characterReferenceLibrary:[],referenceSourceByUrl:{},attachment:null,uploading:[]});

function harness(sharedCache=new Map()){
  const timers=new Map(),requests=[],ta={value:''},errors=[];
  let nextTimer=0;
  const s={imageState:image(),videoState:{modelId:'video-a',startImage:'',endImage:'',referenceImageUrls:[],attachment:null,editUploading:null},
    musicState:{modelId:'music-a',uploads:[],attachment:null},voiceState:{modelId:'voice-a',uploads:[],attachment:null,uploading:null},textState:{modelId:'text-a',attachment:null},
    voiceWorkspaceMode:'voiceover',owner:101,mode:'image',restoringDraft:false,serverDrafts:{},pendingAttachment:null,currentConvId:'image-conv',
    getTelegramId:()=>s.owner,currentChatType:()=>s.mode,activeGenerationLocked:()=>false,
    currentModeAttachment:()=>({image:s.imageState,video:s.videoState,music:s.musicState,voice:s.voiceState,text:s.textState})[s.mode].attachment,
    IMAGE_MODEL_LIST:[{id:'image-a'},{id:'image-b'}],VIDEO_MODELS:[{id:'video-a'}],MUSIC_MODEL_LIST:[{id:'music-a'}],VOICE_MODEL_LIST:[{id:'voice-a'}],TEXT_MODEL_LIST:[{id:'text-a'}],
    document:{getElementById:()=>ta},localStorage:{getItem:key=>sharedCache.get(key)||null,setItem:(key,value)=>sharedCache.set(key,value)},
    setTimeout:fn=>{const id=++nextTimer;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),
    fetch:async(path,options)=>{requests.push({path,payload:JSON.parse(options.body)});return {ok:true,json:async()=>({ok:true})};},
    autoGrow(){},renderImageControls(){},renderVideoControls(){},renderMusicControls(){},renderVoiceControls(){},renderTextControls(){},renderAllUploadPreviews(){},applyVoiceWorkspaceMode(){},updateSendButton(){},
  };
  const ctx=vm.createContext(s);vm.runInContext(source.slice(a,b),ctx);
  return {s,ctx,ta,cache:sharedCache,timers,requests,errors,run:code=>vm.runInContext(code,ctx),
    async flush(){const batch=[...timers.values()];timers.clear();for(const fn of batch)await fn();}};
}

test('a reference-only image draft restores all confirmed files and settings after reload',async()=>{
  const first=harness();
  first.s.imageState.uploadedImageUrls=['https://storage.test/b/generated/a.png#old','https://storage.test/b/generated/b.png#old'];
  first.s.imageState.referenceImageUrls=[...first.s.imageState.uploadedImageUrls];first.s.imageState.modelId='image-b';first.s.imageState.count=4;
  first.run('saveCurrentDraftSoon()');await first.flush();assert.equal(first.requests.length,1);
  const second=harness(first.cache);second.s.serverDrafts={image:first.requests[0].payload};
  second.run('composerDraftOwner=101;applyCurrentDraft()');
  assert.deepEqual(clone(second.s.imageState.uploadedImageUrls),first.s.imageState.uploadedImageUrls);
  assert.equal(second.s.imageState.modelId,'image-b');assert.equal(second.s.imageState.count,4);assert.equal(second.ta.value,'');
  assert.equal(second.requests.length,0,'restoring never uploads or dispatches a generation');
});

test('deferred saves capture the original mode, attachment and conversation before a mode switch',async()=>{
  const h=harness();h.ta.value='Image prompt';h.s.imageState.uploadedImageUrls=['https://storage.test/generated/image.png'];h.run('saveCurrentDraftSoon()');
  h.s.mode='video';h.s.currentConvId='video-conv';h.ta.value='Video prompt';h.s.videoState.startImage='https://storage.test/generated/start.png';h.run('saveCurrentDraftSoon()');
  assert.equal(h.timers.size,2);await h.flush();
  assert.deepEqual(h.requests.map(x=>[x.payload.mode,x.payload.draft_text,x.payload.conversation_id]),[['image','Image prompt','image-conv'],['video','Video prompt','video-conv']]);
  const imageDraft=h.requests[0].payload.attachment.composer_draft;
  assert.equal(imageDraft.state.uploadedImageUrls[0].url,'https://storage.test/generated/image.png');
  assert.ok(!JSON.stringify(imageDraft).includes('start.png'));
});

test('a background image upload saves to image while the video composer is active',async()=>{
  const h=harness();h.s.serverDrafts.image={draft_text:'Saved image prompt',conversation_id:'saved-image'};
  h.s.mode='video';h.s.currentConvId='video-conv';h.ta.value='Video draft';
  h.s.imageState.uploadedImageUrls=['https://storage.test/generated/finished.png'];h.run("saveCurrentDraftSoon('image')");await h.flush();
  assert.equal(h.requests[0].payload.mode,'image');assert.equal(h.requests[0].payload.draft_text,'Saved image prompt');assert.equal(h.requests[0].payload.conversation_id,'saved-image');
});

test('a failed cloud save remains in the same account local cache and restores without reupload',async()=>{
  const h=harness();h.s.fetch=async()=>{throw new Error('offline');};h.s.imageState.uploadedImageUrls=['https://storage.test/generated/offline.png'];h.run('saveCurrentDraftSoon()');await h.flush();
  assert.equal(JSON.parse([...h.cache.values()][0]).pending,true);
  const reload=harness(h.cache);reload.s.serverDrafts=reload.run('mergedComposerDrafts({},101)');reload.run('composerDraftOwner=101;applyCurrentDraft()');
  assert.deepEqual(clone(reload.s.imageState.uploadedImageUrls),['https://storage.test/generated/offline.png']);assert.equal(reload.requests.length,0);
});

test('media arrays and reference-source keys follow the API refreshed signatures',()=>{
  const h=harness(),url='https://storage.test/generated/ref.png#old';
  h.s.imageState.uploadedImageUrls=[url];h.s.imageState.referenceSourceByUrl={[url]:'history'};
  const encoded=clone(h.run('composerDraftAttachment("image")'));
  function sign(value,key=''){if(Array.isArray(value))return value.map(item=>sign(item,key));if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,sign(v,k)]));return key==='url'&&typeof value==='string'?value.replace('#old','#fresh'):value;}
  h.s.serverDrafts.image={attachment:sign(encoded)};h.run('composerDraftOwner=101;applyCurrentDraft()');
  // Existing local inputs win; test a fresh page to verify refreshed restoration.
  const fresh=harness();fresh.s.serverDrafts.image={attachment:sign(encoded)};fresh.run('composerDraftOwner=101;applyCurrentDraft()');
  assert.equal(fresh.s.imageState.uploadedImageUrls[0],url.replace('#old','#fresh'));
  assert.equal(fresh.s.imageState.referenceSourceByUrl[url.replace('#old','#fresh')],'history');
});

test('unconfirmed files, transient uploads and blob/data URLs are never restored as ready inputs',()=>{
  const h=harness();h.s.imageState.uploading=[{previewUrl:'blob:pending'}];h.s.imageState.attachment={uploading:true,file:{name:'pending.png'},url:''};
  h.s.imageState.uploadedImageUrls=['data:image/png;base64,dummy','blob:pending'];
  const attachment=h.run('composerDraftAttachment("image")');
  assert.equal(attachment.composer_draft.state.uploading,undefined);assert.equal(attachment.composer_draft.state.attachment,null);
  assert.ok(!JSON.stringify(attachment).includes('base64'));assert.ok(!JSON.stringify(attachment).includes('blob:'));
});

test('account switch cancels pending writes and clears every private composer input',async()=>{
  const h=harness();h.s.imageState.uploadedImageUrls=['https://storage.test/generated/private.png'];h.s.videoState.startImage='https://storage.test/generated/private-video.png';h.run('saveCurrentDraftSoon()');
  h.s.owner=202;h.run('resetComposerDraftOwner()');await h.flush();
  assert.equal(h.requests.length,0);assert.deepEqual(clone(h.s.imageState.uploadedImageUrls),[]);assert.equal(h.s.videoState.startImage,'');
  assert.deepEqual(clone(h.run('mergedComposerDrafts({},202)')),{});
});

test('a queued write never follows a different signed-in account',async()=>{
  const h=harness();h.run('saveCurrentDraftSoon()');h.s.owner=202;await h.flush();assert.equal(h.requests.length,0);
});

test('late sync preserves newly selected models and confirmed inputs',()=>{
  const first=harness();first.s.imageState.modelId='image-b';first.s.imageState.uploadedImageUrls=['https://storage.test/generated/old.png'];const saved=first.run('composerDraftAttachment("image")');
  const late=harness();late.s.serverDrafts.image={attachment:saved};late.s.imageState.uploadedImageUrls=['https://storage.test/generated/new.png'];late.s.imageState.size='16:9';
  late.run('composerDraftOwner=101;applyCurrentDraft()');assert.deepEqual(clone(late.s.imageState.uploadedImageUrls),['https://storage.test/generated/new.png']);assert.equal(late.s.imageState.size,'16:9');
});

test('startup and repeated rendering do not overwrite the saved draft or enqueue duplicate writes',()=>{
  const h=harness();h.run('saveComposerDraftIfChanged()');assert.equal(h.timers.size,0);
  h.run('composerDraftOwner=101;applyCurrentDraft();saveComposerDraftIfChanged()');assert.equal(h.timers.size,0);
  h.s.imageState.count=4;h.run('saveComposerDraftIfChanged();saveComposerDraftIfChanged();saveComposerDraftIfChanged()');assert.equal(h.timers.size,1);
});

for(const mode of ['video','music','voice','text'])test(`${mode} restores its own saved settings and stored media`,()=>{
  const h=harness();h.s.mode=mode;const state=h.s[mode+'State'];state.attachment={kind:mode==='text'?'file':'audio',url:'https://storage.test/generated/'+mode+'.bin'};
  const saved=h.run(`composerDraftAttachment('${mode}')`),reload=harness();reload.s.mode=mode;reload.s.serverDrafts[mode]={attachment:saved};reload.run('composerDraftOwner=101;applyCurrentDraft()');
  assert.equal(reload.s[mode+'State'].attachment.url,'https://storage.test/generated/'+mode+'.bin');assert.equal(reload.s.imageState.attachment,null);
});


test('the real image option renderer saves a model selection even when the prompt is unchanged',async()=>{
  const h=harness();
  h.s.currentImageModel=()=>({id:h.s.imageState.modelId});
  h.s.syncImageModelOptionDefaults=()=>{};h.s.isImageMode=()=>true;
  h.s.updateComposerModelDisplay=()=>{};h.s.renderImageReferenceSections=()=>{};
  h.run('composerDraftOwner=101;applyCurrentDraft()');
  const match=source.match(/^( *)function renderImageControls\(\) \{/m),start=match.index;
  const tail=source.slice(start+match[0].length),end=tail.search(new RegExp('^'+match[1]+'\\}$','m'));
  vm.runInContext(source.slice(start,start+match[0].length+end+match[1].length+1),h.ctx);
  h.s.document.getElementById=id=>id==='chatInput'?h.ta:null;
  // The model menu renders the controls, without editing the prompt or clicking Generate.
  h.s.imageState.modelId='image-b';h.run('renderImageControls()');await h.flush();
  assert.equal(h.requests.length,1);
  assert.equal(h.requests[0].payload.attachment.composer_draft.state.modelId,'image-b');
  assert.equal(h.requests[0].payload.draft_text,'');
  const reload=harness();reload.s.serverDrafts.image=h.requests[0].payload;
  reload.run('composerDraftOwner=101;applyCurrentDraft()');assert.equal(reload.s.imageState.modelId,'image-b');
});


test('mode transitions restore each prompt before automatic saves and never write the previous mode text',async()=>{
  const h=harness();h.run('composerDraftOwner=101;applyCurrentDraft()');
  h.ta.value='Image only';h.s.imageState.uploadedImageUrls=['https://storage.test/generated/image.png'];h.run('saveCurrentDraftSoon()');await h.flush();
  h.s.mode='text';h.run('saveComposerDraftIfChanged();applyCurrentDraft()');assert.equal(h.ta.value,'');
  h.ta.value='Text only';h.run('saveCurrentDraftSoon()');await h.flush();
  for(let i=0;i<3;i++) {
    h.s.mode='image';h.run('saveComposerDraftIfChanged();applyCurrentDraft();saveComposerDraftIfChanged()');assert.equal(h.ta.value,'Image only');
    h.s.mode='text';h.run('saveComposerDraftIfChanged();applyCurrentDraft();saveComposerDraftIfChanged()');assert.equal(h.ta.value,'Text only');
  }
  await h.flush();assert.deepEqual(h.requests.map(x=>[x.payload.mode,x.payload.draft_text]),[['image','Image only'],['text','Text only']]);
  assert.deepEqual(clone(h.s.imageState.uploadedImageUrls),['https://storage.test/generated/image.png']);
});
