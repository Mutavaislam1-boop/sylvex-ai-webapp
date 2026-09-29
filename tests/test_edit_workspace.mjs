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
test('camera presets, ranges and drag math share exact coordinates',()=>{
 const h=harness();h.context.setEditCameraPreset(null,270,0);assert.equal(h.state.camera.horizontal,270);
 h.context.updateEditWorkspaceRange({currentTarget:{value:'42.7'}},'camera','vertical');assert.equal(h.state.camera.vertical,42.7);
 h.context.updateEditCamera({zoom:0});assert.equal(h.state.camera.zoom,0);
 for(const angle of [0,1,45,90,179,180,270,359]){
  const p=h.context.editCameraProject(angle,0,140),actual=h.context.editCameraHorizontalAt(p);
  assert.ok(Math.abs(((actual-angle+540)%360)-180)<.0001,`${angle} -> ${actual}`);
 }
 for(const vertical of [-30,0,30,60,90]){
  const p=h.context.editCameraProject(45,vertical,100);
  assert.ok(Math.abs(h.context.editCameraVerticalAt(p,45,vertical)-vertical)<.26);
 }
 for(const zoom of [0,1.3,5,10]){
  const camera={horizontal:135,vertical:32,zoom};const geometry=h.context.editCameraGeometry(camera);
  assert.ok(Math.abs(h.context.editCameraZoomAt(geometry.camera,camera)-zoom)<.001);
 }
});
test('camera uses full circle, clamps unsupported elevation, and preserves numeric zero',()=>{
 const h=harness();h.context.updateEditCamera({horizontal:360,vertical:-90,zoom:0});
 assert.equal(h.state.camera.horizontal,360);assert.equal(h.state.camera.vertical,-30);assert.equal(h.state.camera.zoom,0);
 const front=h.context.editCameraGeometry({horizontal:0,vertical:0,zoom:5}),full=h.context.editCameraGeometry({horizontal:360,vertical:0,zoom:5});
 assert.ok(Math.abs(front.camera.x-full.camera.x)<.00001);
});
test('camera request, prompt and state agree; canvas pan and scale never affect generation',async()=>{
 const h=harness();h.state.mode='camera';h.context.updateEditCamera({horizontal:217.4,vertical:38.2,zoom:6.7});
 h.state.viewport={x:300,y:-120};h.context.editWorkspaceSetViewZoom(175);await h.context.generateEditWorkspace();
 const [prompt,,, , options]=h.requests[0];
 assert.match(prompt,/217.4 degrees/);assert.match(prompt,/38.2 degrees/);assert.match(prompt,/6.7\/10/);
 assert.equal(options.imageOptions.editWorkspaceCamera.horizontal,217.4);assert.equal(options.imageOptions.editWorkspaceCamera.vertical,38.2);assert.equal(options.imageOptions.editWorkspaceCamera.zoom,6.7);
 assert.equal(options.imageOptions.viewport,undefined);assert.equal(options.imageOptions.zoom,undefined);assert.equal(options.isolateRequest,true);
});
test('zoom anchors the object under the pointer and Fit returns it to center',()=>{
 const h=harness();h.state.viewport={x:30,y:20};h.context.editWorkspaceSetViewZoom(200,{x:100,y:80});
 assert.equal(h.state.viewport.x,-40);assert.equal(h.state.viewport.y,-40);
 h.context.fitEditWorkspace();assert.equal(h.state.zoom,100);assert.equal(h.state.viewport.x,0);assert.equal(h.state.camera.zoom,5);
});
test('camera settings survive tool changes and cannot be modified during generation',()=>{
 const h=harness();h.context.updateEditCamera({horizontal:122,vertical:11,zoom:2.5});h.context.setEditWorkspaceMode(null,'retouch');h.context.setEditWorkspaceMode(null,'camera');
 assert.equal(h.state.camera.horizontal,122);h.state.busy=true;h.context.updateEditCamera({horizontal:90});assert.equal(h.state.camera.horizontal,122);
});
