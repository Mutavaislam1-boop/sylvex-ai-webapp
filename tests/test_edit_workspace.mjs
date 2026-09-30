import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../webapp/js/cabinet.js',import.meta.url),'utf8');
const block=source.slice(source.indexOf('function createEditWorkspaceState'),source.indexOf('\nasync function generateQuickImageDetail',source.indexOf('function createEditWorkspaceState')));
function harness(){
  const requests=[],messages=[],revoked=[];let rejectUpload=false;
  const context=vm.createContext({console,URL:{createObjectURL:()=> 'blob:new',revokeObjectURL:u=>revoked.push(u)},
    Image:class{naturalWidth=1200;naturalHeight=800;set src(value){queueMicrotask(()=>this.onload());}},
    document:{getElementById:id=>id==='editWorkspaceMask'?{toDataURL:()=> 'data:image/png;base64,MASK'}:null,body:{classList:{add(){},remove(){}}}},
    toast:m=>messages.push(m),updateComposerMode(){},callGenerate:async (...args)=>{requests.push(args);return {images:['https://cdn.example/result.png']};},
    uploadProStudioMediaFile:async ()=>{if(rejectUpload)throw new Error('upload failed');return 'https://cdn.example/new.png';},
    activeGenerationPlaceholderIndex:()=>-1,generatedUrlsFromResponse:r=>r.images,generatedThumbsFromResponse:()=>[],addGeneratedImages(){},imageGenerationMetadata:()=>({}),loadConversations(){},chatMessages:[],resolveFailureMessage:e=>({error:e.message}),translateGenerationError:e=>e.message,clearActiveProStudioJob(){},renderChat(){},rememberCurrentChatSpace(){},
  });
  vm.runInContext(block+'\nconst editWorkspaceState=createEditWorkspaceState();renderEditWorkspace=()=>{};drawEditWorkspaceMask=()=>{};updateEditWorkspaceReady=()=>{};this.state=editWorkspaceState;',context);
  Object.assign(context.state,{sourceUrl:'https://cdn.example/source.png',sourcePreview:'https://cdn.example/source.png',width:1200,height:800,prompt:'Turn blue'});
  return {context,state:context.state,requests,messages,revoked,failUpload:()=>{rejectUpload=true;}};
}
test('mode-specific prompts persist independently',()=>{const h=harness();h.context.setEditWorkspaceMode(null,'translate');assert.equal(h.state.prompt,'');h.context.setEditWorkspaceMode(null,'edit');assert.equal(h.state.prompt,'Turn blue');});
test('retouch requires selection; erase does not require a prompt',()=>{const h=harness();h.state.mode='retouch';h.state.brushMode='erase';h.state.prompt='';assert.match(h.context.editWorkspaceValidation(),/кистью/);h.state.maskStrokes=[{points:[{x:.5,y:.5}]}];assert.equal(h.context.editWorkspaceValidation(),'');});
test('retouch sends mask; next generation uses result, and undo restores previous source',async()=>{
 const h=harness();h.state.mode='retouch';h.state.maskStrokes=[{points:[{x:.5,y:.5}]}];await h.context.generateEditWorkspace();
 assert.equal(h.requests[0][4].imageOptions.editWorkspaceMaskUrl,'data:image/png;base64,MASK');assert.equal(h.requests[0][4].isolateRequest,true);
 assert.equal(h.state.sourceUrl,'https://cdn.example/result.png');assert.equal(h.state.maskStrokes.length,0);
 h.context.setEditWorkspaceDimensions(1200,800);h.context.setEditWorkspaceMode(null,'edit');h.state.prompt='Next edit';await h.context.generateEditWorkspace();assert.equal(h.requests[1][2][0],'https://cdn.example/result.png');
 h.context.undoEditWorkspace();h.context.undoEditWorkspace();assert.equal(h.state.sourceUrl,'https://cdn.example/source.png');
});
test('failed generation preserves the editable source and previous result',async()=>{const h=harness();h.state.resultUrl='https://cdn.example/previous.png';h.context.callGenerate=async()=>{throw new Error('provider failed');};await h.context.generateEditWorkspace();assert.equal(h.state.resultUrl,'https://cdn.example/previous.png');assert.equal(h.state.history.length,0);assert.equal(h.state.busy,false);});
test('busy workspace cannot switch modes, alter settings or start another request',async()=>{const h=harness();h.state.busy=true;h.context.setEditWorkspaceMode(null,'camera');h.context.setEditCameraPreset(null,90,10);await h.context.generateEditWorkspace();assert.equal(h.state.mode,'edit');assert.equal(h.state.camera.horizontal,0);assert.equal(h.requests.length,0);});
test('resize keeps ratio unless unlocked; expansion accepts zero margin',()=>{const h=harness();h.context.updateEditWorkspaceField({currentTarget:{type:'number',value:'600'}},'resize','width');assert.equal(h.state.resize.height,400);h.state.resize.locked=false;h.context.updateEditWorkspaceField({currentTarget:{type:'number',value:'300'}},'resize','width');assert.equal(h.state.resize.height,400);h.context.updateEditWorkspaceField({currentTarget:{type:'number',value:'0'}},'expand','left');assert.equal(h.state.expand.left,0);});
test('failed upload preserves existing document, successful upload resets selection',async()=>{const h=harness();h.failUpload();await h.context.loadEditWorkspaceImage({name:'new.png',type:'image/png',size:10});assert.equal(h.state.sourceUrl,'https://cdn.example/source.png');assert.equal(h.state.uploading,false);assert.deepEqual(h.revoked,['blob:new']);const ok=harness();ok.state.maskStrokes=[{}];await ok.context.loadEditWorkspaceImage({name:'new.png',type:'image/png',size:10});assert.equal(ok.state.sourceUrl,'https://cdn.example/new.png');assert.equal(ok.state.maskStrokes.length,0);assert.equal(ok.state.resize.width,1200);});
test('lights are limited to eight and all-disabled is rejected',()=>{const h=harness();h.state.mode='lighting';for(let i=0;i<12;i++)h.context.addEditWorkspaceLight();assert.equal(h.state.light.layers.length,8);h.state.light.layers.forEach(l=>l.enabled=false);assert.match(h.context.editWorkspaceValidation(),/источник/);});
test('comparison view cannot submit a retouch without its visible mask canvas',async()=>{const h=harness();h.state.mode='retouch';h.state.maskStrokes=[{}];h.state.showBefore=true;await h.context.generateEditWorkspace();assert.equal(h.requests.length,0);assert.match(h.messages[0],/Вернитесь к результату/);});
test('completed job downloads through the protected file endpoint',async()=>{const h=harness();const downloads=[];h.state.resultUrl='https://cdn.example/result.png';h.state.jobId='job-123';h.context.completedGenerationDownloadUrl=id=>'/download/'+id;h.context.downloadGeneratedFile=event=>downloads.push(event.currentTarget.dataset);await h.context.downloadEditWorkspaceResult();assert.equal(downloads[0].downloadUrl,'/download/job-123');});
test('brush strokes can be undone and redone; clearing resets both stacks',()=>{const h=harness();const stroke={points:[{x:.2,y:.4}],size:.05};h.state.maskStrokes=[stroke];h.context.clearEditWorkspaceMask(null,true);assert.equal(h.state.maskStrokes.length,0);h.context.redoEditWorkspaceMask();assert.equal(h.state.maskStrokes[0],stroke);h.context.clearEditWorkspaceMask();assert.equal(h.state.maskStrokes.length,0);assert.equal(h.state.maskRedo.length,0);});
test('shared request builder preserves isolated masks without reading composer state',async()=>{
 const builder=source.slice(source.indexOf('async function buildGenerationRequest('),source.indexOf('\nasync function callGenerateCore(',source.indexOf('async function buildGenerationRequest(')));
 const context=vm.createContext({getTelegramId:()=>123,currentConvId:'conversation',uiLang:()=> 'ru'});
 vm.runInContext(builder,context);
 const mask='data:image/png;base64,TEST';
 const result=await context.buildGenerationRequest({mode:'image',prompt:'Edit · Retouch',imageOptions:{tool:'edit_workspace',editWorkspaceMaskUrl:mask,referenceImageUrls:['https://cdn.example/source.png']},generationOptions:{isolateRequest:true}});
 assert.equal(result.payload.image_options.editWorkspaceMaskUrl,mask);
 assert.equal(result.payload.image_options.style,undefined);
 assert.equal(result.payload.image_options.characterReferences,undefined);
});
