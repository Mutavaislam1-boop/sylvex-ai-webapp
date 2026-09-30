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
test('Fit uses the unobscured area without moving an asymmetric expanded source off center',()=>{
 const h=harness(),area={width:800,height:500,x:-200,y:-20};
 const fit=h.context.editWorkspaceFitView(area,{width:1200,height:800},{left:400,right:0,top:0,bottom:200});
 assert.equal(fit.zoom,50);assert.equal(fit.viewport.x,-100);assert.equal(fit.viewport.y,-70);
 assert.equal(fit.viewport.x+(0-400)*.5/2,area.x);
 assert.equal(fit.viewport.y+(200-0)*.5/2,area.y);
});
function navigationHarness(){
 const h=harness(),listeners={},classes=new Set(),captured=new Set();let paints=0;
 const root={_editView:()=>paints++,querySelector:()=>null};
 h.context.document.getElementById=id=>id==='editWorkspace'?root:null;
 h.context.document.addEventListener=(type,fn)=>listeners['document:'+type]=fn;
 h.context.document.removeEventListener=type=>delete listeners['document:'+type];
 h.context.window={addEventListener:(type,fn)=>listeners['window:'+type]=fn,removeEventListener:type=>delete listeners['window:'+type]};
 const stage={tabIndex:-1,setAttribute(){},focus(){},classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)},
  setPointerCapture:id=>captured.add(id),hasPointerCapture:id=>captured.has(id),releasePointerCapture:id=>captured.delete(id),
  getBoundingClientRect:()=>({left:0,top:0,width:1400,height:900}),addEventListener:(type,fn)=>listeners[type]=fn};
 const cleanup=h.context.initEditWorkspaceNavigation(stage);
 const event=(overrides={})=>({pointerId:1,button:0,clientX:300,clientY:200,deltaX:0,deltaY:0,deltaMode:0,target:{closest:()=>null},preventDefault(){},...overrides});
 return {...h,stage,listeners,classes,captured,event,cleanup,paints:()=>paints};
}
test('drag pans the world without bounds and releases pointer capture',()=>{
 const h=navigationHarness();h.stage.onpointerdown(h.event());h.stage.onpointermove(h.event({clientX:5300,clientY:-2800}));
 assert.equal(h.state.viewport.x,5000);assert.equal(h.state.viewport.y,-3000);assert.ok(h.paints()>0);
 h.stage.onpointerup(h.event());assert.equal(h.captured.size,0);assert.ok(!h.classes.has('is-panning'));
 h.stage.onpointermove(h.event({clientX:0}));assert.equal(h.state.viewport.x,5000);
});
test('trackpad scroll pans, modifier scroll zooms at cursor, and tool switches preserve view',()=>{
 const h=navigationHarness();h.listeners.wheel(h.event({deltaX:70,deltaY:110}));
 assert.equal(h.state.viewport.x,-70);assert.equal(h.state.viewport.y,-110);assert.equal(h.state.zoom,100);
 const anchor={x:-400,y:-250},world={x:anchor.x+70,y:anchor.y+110};
 h.listeners.wheel(h.event({ctrlKey:true,deltaY:-100}));
 assert.ok(Math.abs((anchor.x-h.state.viewport.x)/(h.state.zoom/100)-world.x)<1e-9);
 assert.ok(Math.abs((anchor.y-h.state.viewport.y)/(h.state.zoom/100)-world.y)<1e-9);
 const view=JSON.stringify({zoom:h.state.zoom,viewport:h.state.viewport});
 for(const mode of ['camera','lighting','retouch','expand'])h.context.setEditWorkspaceMode(null,mode);
 assert.equal(JSON.stringify({zoom:h.state.zoom,viewport:h.state.viewport}),view);
});
test('retouch background and Space pan while the mask keeps normal strokes; listeners are cleaned up',()=>{
 const h=navigationHarness();h.state.mode='retouch';
 const mask={closest:selector=>selector==='#editWorkspaceMask'?{}:null};
 h.stage.onpointerdown(h.event({target:mask}));assert.equal(h.captured.size,0);
 h.listeners['document:keydown'](h.event({code:'Space'}));
 h.stage.onpointerdown(h.event({target:mask}));assert.equal(h.captured.size,1);
 h.stage.onpointercancel(h.event());h.listeners['document:keyup'](h.event({code:'Space'}));
 h.stage.onpointerdown(h.event());assert.equal(h.captured.size,1);
 h.stage.onpointerup(h.event());h.state.busy=true;
 const view=JSON.stringify(h.state.viewport);h.listeners.wheel(h.event({deltaY:80}));h.stage.onkeydown(h.event({key:'+'}));
 assert.equal(JSON.stringify(h.state.viewport),view);assert.equal(h.state.zoom,100);
 h.cleanup();assert.ok(!h.listeners['document:keydown']);assert.ok(!h.listeners['document:keyup']);assert.ok(!h.listeners['window:blur']);
});
test('camera settings survive tool changes and cannot be modified during generation',()=>{
 const h=harness();h.context.updateEditCamera({horizontal:122,vertical:11,zoom:2.5});h.context.setEditWorkspaceMode(null,'retouch');h.context.setEditWorkspaceMode(null,'camera');
 assert.equal(h.state.camera.horizontal,122);h.state.busy=true;h.context.updateEditCamera({horizontal:90});assert.equal(h.state.camera.horizontal,122);
});
test('light presets and ranges update only the selected source and preserve color and brightness',()=>{
 const h=harness();h.context.updateEditLight({color:'#AABBCC',brightness:1.7});
 h.context.addEditWorkspaceLight();h.context.setEditLightPreset(null,270,-90);
 h.context.updateEditWorkspaceRange({currentTarget:{value:'217.4'}},'light','horizontal');
 h.context.updateEditWorkspaceRange({currentTarget:{value:'38.2'}},'light','vertical');
 assert.equal(h.state.light.layers[1].horizontal,217.4);assert.equal(h.state.light.layers[1].vertical,38.2);
 h.context.selectEditWorkspaceLight(null,0);
 assert.equal(h.state.light.layers[0].horizontal,45);assert.equal(h.state.light.layers[0].brightness,1.7);assert.equal(h.state.light.layers[0].color,'#aabbcc');
 h.context.setEditWorkspaceMode(null,'camera');h.context.setEditWorkspaceMode(null,'lighting');
 assert.equal(h.state.light.layers[1].horizontal,217.4);assert.equal(h.state.camera.horizontal,0);
});
test('lighting drag math covers full horizontal orbit and both ends of the vertical half-orbit',()=>{
 const h=harness();
 for(const horizontal of [0,45,90,135,180,270,359])for(const vertical of [-90,-60,-30,0,30,60,90]){
  const point=h.context.editCameraProject(horizontal,vertical,100);
  const actual=h.context.editCameraVerticalAt(point,horizontal,vertical,-90,90);
  assert.ok(Math.abs(actual-vertical)<.26,`${horizontal}/${vertical} -> ${actual}`);
 }
 h.context.updateEditLight({horizontal:360,vertical:-90,brightness:0});
 assert.equal(h.state.light.layers[0].horizontal,360);assert.equal(h.state.light.layers[0].vertical,-90);assert.equal(h.state.light.layers[0].brightness,0);
 h.state.mode='lighting';assert.match(h.context.editWorkspaceValidation(),/источник/);
});
test('light color input validates HEX and controls cannot mutate a busy workspace',()=>{
 const h=harness();h.context.updateEditLightHex({currentTarget:{value:'#F0aF17'}});assert.equal(h.state.light.layers[0].color,'#f0af17');
 h.context.updateEditLightHex({currentTarget:{value:'invalid'}});assert.equal(h.state.light.layers[0].color,'#f0af17');assert.match(h.messages[0],/#RRGGBB/);
 const saved=JSON.stringify(h.state.light);h.state.busy=true;
 h.context.updateEditLightColor({currentTarget:{value:'#abcdef'}});h.context.setEditLightPreset(null,180,90);
 h.context.addEditWorkspaceLight();h.context.removeEditWorkspaceLight();h.context.toggleEditWorkspaceLight();
 assert.equal(JSON.stringify(h.state.light),saved);
});
test('disabled and zero-brightness lights are excluded from the prompt; exact settings reach generation',async()=>{
 const h=harness();h.state.mode='lighting';h.context.updateEditLight({horizontal:217.4,vertical:-38.2,brightness:1.7,color:'#6633cc'});
 h.context.addEditWorkspaceLight();h.context.updateEditLight({color:'#ff0000'});h.context.toggleEditWorkspaceLight();
 h.context.addEditWorkspaceLight();h.context.updateEditLight({color:'#00ff00',brightness:0});
 h.state.viewport={x:450,y:120};h.context.editWorkspaceSetViewZoom(50);await h.context.generateEditWorkspace();
 const [prompt,,,,options]=h.requests[0],lighting=options.imageOptions.editWorkspaceLight;
 assert.match(prompt,/1 light source/);assert.match(prompt,/217.4 degrees/);assert.match(prompt,/-38.2 degrees/);assert.match(prompt,/brightness 1.7\/2/);
 assert.ok(!prompt.includes('#ff0000')&&!prompt.includes('#00ff00'));assert.equal(lighting.coordinateSystem,'spherical-degrees');
 assert.equal(lighting.layers[0].horizontal,217.4);assert.equal(lighting.layers[0].brightness,1.7);assert.equal(options.model,'iclight_v2');
 h.context.selectEditWorkspaceLight(null,0);h.context.updateEditLight({brightness:.2});assert.equal(lighting.layers[0].brightness,1.7,'request retains an immutable settings snapshot');
});
test('removing a light preserves remaining settings, and adding after an off source creates an enabled light',()=>{
 const h=harness();h.context.updateEditLight({horizontal:122,color:'#aabbcc'});h.context.addEditWorkspaceLight();h.context.updateEditLight({horizontal:241,color:'#112233'});
 h.context.selectEditWorkspaceLight(null,0);h.context.removeEditWorkspaceLight();
 assert.equal(h.state.light.layers.length,1);assert.equal(h.state.light.layers[0].horizontal,241);assert.equal(h.state.light.active,0);
 h.context.removeEditWorkspaceLight();assert.equal(h.state.light.layers.length,1);
 h.context.toggleEditWorkspaceLight();h.context.addEditWorkspaceLight();assert.equal(h.state.light.layers[1].enabled,true);assert.equal(h.state.light.layers[1].brightness,1);
});
