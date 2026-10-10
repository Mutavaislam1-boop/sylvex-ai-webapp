import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../webapp/js/cabinet.js',import.meta.url),'utf8');
const block=source.slice(source.indexOf('function createEditWorkspaceState'),source.indexOf('\nasync function generateQuickImageDetail',source.indexOf('function createEditWorkspaceState')));
function harness(){
  const requests=[],messages=[],revoked=[];let rejectUpload=false;
  const context=vm.createContext({console,setTimeout,clearTimeout,URL:{createObjectURL:()=> 'blob:new',revokeObjectURL:u=>revoked.push(u)},
    Image:class{naturalWidth=1200;naturalHeight=800;set src(value){queueMicrotask(()=>this.onload());}},
    document:{querySelector:()=>null,getElementById:id=>id==='editWorkspaceMask'?{toDataURL:()=> 'data:image/png;base64,MASK'}:null,body:{classList:{add(){},remove(){}}}},
    toast:m=>messages.push(m),updateComposerMode(){},callGenerate:async (...args)=>{requests.push(args);return {images:['https://cdn.example/result.png']};},
    uploadProStudioMediaFile:async ()=>{if(rejectUpload)throw new Error('upload failed');return 'https://cdn.example/new.png';},
    activeGenerationPlaceholderIndex:()=>-1,generatedUrlsFromResponse:r=>r.images,generatedThumbsFromResponse:()=>[],addGeneratedImages(){},imageGenerationMetadata:()=>({}),loadConversations(){},chatMessages:[],resolveFailureMessage:e=>({error:e.message}),translateGenerationError:e=>e.message,clearActiveProStudioJob(){},renderChat(){},rememberCurrentChatSpace(){},
  });
  vm.runInContext(block+'\nconst editWorkspaceState=createEditWorkspaceState();renderEditWorkspace=()=>{};drawEditWorkspaceMask=()=>{};updateEditWorkspaceReady=()=>{};this.state=editWorkspaceState;',context);
  Object.assign(context.state,{sourceUrl:'https://cdn.example/source.png',sourcePreview:'https://cdn.example/source.png',width:1200,height:800,prompt:'Turn blue'});
  return {context,state:context.state,requests,messages,revoked,failUpload:()=>{rejectUpload=true;}};
}
test('mode-specific prompts persist independently',()=>{const h=harness();h.context.setEditWorkspaceMode(null,'translate');assert.equal(h.state.prompt,'');h.context.setEditWorkspaceMode(null,'edit');assert.equal(h.state.prompt,'Turn blue');});
test('Background modes isolate drafts and custom backdrop from other image tools',async()=>{
 for(const mode of ['transparent','replace','color','image']){
  const h=harness();h.state.mode='background';h.state.prompt='A beach at sunset';
  h.state.background={color:'#123abc',url:'https://cdn.example/background.png',name:'Beach'};
  h.context.setEditBackgroundMode(null,mode);await h.context.generateEditWorkspace();
  const request=h.requests[0],opts=request[4].imageOptions;
  assert.equal(opts.editWorkspacePrompt,mode==='replace'?'A beach at sunset':'');
  assert.equal(request[0].includes('A beach at sunset'),mode==='replace');
  assert.equal(opts.editWorkspaceBackground.color,mode==='color'?'#123abc':undefined);
  assert.equal(opts.editWorkspaceBackground.url,mode==='image'?'https://cdn.example/background.png':undefined);
  assert.equal(request[2].length,1);assert.equal(request[2][0],'https://cdn.example/source.png');
  assert.equal(h.state.chain.length,2);assert.equal(h.state.chain[1].parentId,h.state.chain[0].id);
  h.context.setEditBackgroundMode(null,'replace');assert.equal(h.state.prompt,'A beach at sunset');
 }
 const h=harness();h.state.background.url='https://cdn.example/unrelated.png';h.state.mode='camera';
 await h.context.generateEditWorkspace();assert.equal(Object.keys(h.requests[0][4].imageOptions.editWorkspaceBackground).length,0);
});
test('Background validates color/photo, rejects unknown modes and locks controls during work',async()=>{
 const h=harness();h.state.mode='background';h.context.setEditBackgroundMode(null,'image');
 await h.context.generateEditWorkspace();assert.equal(h.requests.length,0);assert.match(h.messages[0],/нового фона/);
 h.context.setEditBackgroundMode(null,'color');h.context.updateEditBackgroundColor({currentTarget:{value:'#bad'}});
 assert.match(h.context.editWorkspaceValidation(),/#RRGGBB/);
 h.context.updateEditBackgroundColor(null,'#12ABef');assert.equal(h.context.editWorkspaceValidation(),'');assert.equal(h.state.background.color,'#12abef');
 h.context.setEditBackgroundMode(null,'nonsense');assert.equal(h.state.backgroundMode,'color');
 h.state.busy=true;h.context.setEditBackgroundMode(null,'transparent');h.context.updateEditBackgroundColor(null,'#ffffff');h.context.clearEditBackgroundImage();
 assert.equal(h.state.backgroundMode,'color');assert.equal(h.state.background.color,'#12abef');
});
test('uploading a backdrop never replaces the source or chain and failure preserves the previous backdrop',async()=>{
 const h=harness();h.context.ensureEditWorkspaceChain();
 const chain=JSON.stringify(h.state.chain),session=h.state.sessionId,sourceUrl=h.state.sourceUrl;
 await h.context.loadEditBackgroundImage({name:'Background.png',type:'image/png',size:10});
 assert.equal(h.state.background.url,'https://cdn.example/new.png');assert.equal(h.state.background.name,'Background.png');
 assert.equal(h.state.sessionId,session);assert.equal(h.state.sourceUrl,sourceUrl);assert.equal(JSON.stringify(h.state.chain),chain);
 assert.deepEqual(h.revoked,['blob:new']);assert.equal(h.state.uploading,false);
 h.failUpload();await h.context.loadEditBackgroundImage({name:'Fail.png',type:'image/png',size:10});
 assert.equal(h.state.background.name,'Background.png');assert.equal(h.state.uploading,false);
 h.context.clearEditBackgroundImage();assert.equal(h.state.background.url,'');assert.equal(JSON.stringify(h.state.chain),chain);
});
test('Background rejects unsupported or oversized uploads before touching the current workspace',async()=>{
 const h=harness();h.state.background.url='https://cdn.example/previous.png';
 for(const file of [{type:'image/svg+xml',size:10},{type:'image/png',size:51*1024*1024}])await h.context.loadEditBackgroundImage(file);
 assert.equal(h.state.background.url,'https://cdn.example/previous.png');assert.equal(h.revoked.length,0);assert.equal(h.messages.length,2);
});
test('compact Background replacement keeps its selected photo or color until explicitly cleared',async()=>{
 const h=harness();h.state.mode='background';h.state.prompt='A quiet studio';
 h.context.setEditBackgroundMode(null,'replace');
 await h.context.loadEditBackgroundImage({name:'Background.png',type:'image/png',size:10});
 assert.equal(h.state.backgroundMode,'image');
 h.context.setEditBackgroundMode(null,'replace');assert.equal(h.state.backgroundMode,'image');
 h.context.updateEditBackgroundColor(null,'#2456ab');assert.equal(h.state.backgroundMode,'color');
 h.context.setEditBackgroundMode(null,'replace');assert.equal(h.state.backgroundMode,'color');
 assert.equal(h.context.editBackgroundOptions(h.state).url,undefined);
 h.context.clearEditBackgroundImage();
 assert.equal(h.state.backgroundMode,'replace');assert.equal(h.state.background.url,'');assert.equal(h.state.background.color,'#ffffff');
 assert.equal(h.context.editBackgroundPrompt(h.state),'A quiet studio');
 assert.equal(h.context.editBackgroundColorText('#ffffff'),'#000000');assert.equal(h.context.editBackgroundColorText('#000000'),'#ffffff');
});
test('Background settings and drafts survive session restore; older canvases get safe defaults',()=>{
 const h=harness();h.context.ensureEditWorkspaceChain();h.state.mode='background';h.state.backgroundMode='image';
 h.state.background={color:'#dbeafe',url:'https://cdn.example/background.png',name:'Room.png'};
 const saved=h.context.editSessionSnapshot();h.context.restoreEditSessionState(saved);
 assert.equal(h.state.background.url,saved.background.url);assert.equal(h.state.prompt,saved.prompt);
 delete saved.background;h.context.restoreEditSessionState(saved);
 assert.equal(h.state.background.color,'#ffffff');assert.equal(h.state.background.url,'');
});
test('Generate reserves a connected slot immediately, then fills that same slot without replacing the source',async()=>{
 const h=harness();let finish;h.context.callGenerate=async(...args)=>{h.requests.push(args);return new Promise(resolve=>{finish=resolve;});};
 const pending=h.context.generateEditWorkspace();
 assert.equal(h.state.chain.length,2);const [reference,slot]=h.state.chain;
 assert.equal(reference.url,'https://cdn.example/source.png');assert.equal(slot.parentId,reference.id);assert.equal(slot.status,'pending');assert.equal(slot.url,'');
 const position={x:slot.x,y:slot.y,width:slot.slotWidth,height:slot.slotHeight};assert.ok(slot.x>reference.x);assert.equal(h.state.sourceUrl,reference.url);
 await h.context.generateEditWorkspace();assert.equal(h.requests.length,1);assert.equal(h.state.chain.length,2);
 finish({images:['https://cdn.example/camera.png'],job_id:'camera-job'});await pending;
 assert.equal(h.state.chain[1],slot);assert.equal(slot.status,'ready');assert.equal(slot.url,'https://cdn.example/camera.png');assert.equal(slot.jobId,'camera-job');
 assert.deepEqual({x:slot.x,y:slot.y,width:slot.slotWidth,height:slot.slotHeight},position);assert.equal(reference.url,'https://cdn.example/source.png');assert.equal(h.state.activeNodeId,slot.id);
});
test('camera, lighting and resize append one sequence and send only the preceding successful result',async()=>{
 const h=harness();let index=0;h.context.callGenerate=async(...args)=>{h.requests.push(args);return {images:['https://cdn.example/result-'+(++index)+'.png']};};
 for(const mode of ['camera','lighting','resize']){h.context.setEditWorkspaceMode(null,mode);h.context.setEditWorkspaceDimensions(1200,800);await h.context.generateEditWorkspace();}
 assert.equal(h.state.chain.length,4);
 for(let i=1;i<4;i++){assert.equal(h.state.chain[i].parentId,h.state.chain[i-1].id);assert.equal(h.requests[i-1][2][0],h.state.chain[i-1].url);assert.ok(h.state.chain[i].x>h.state.chain[i-1].x);}
 assert.equal(h.state.chain[0].url,'https://cdn.example/source.png');assert.equal(h.state.chain[3].url,'https://cdn.example/result-3.png');
 assert.equal(h.requests[0][4].model,'gpt_image_2_5_sunburst');assert.equal(h.requests[2][4].imageOptions.editWorkspaceResize.width,1200);
 assert.ok(h.requests.every(request=>!('chain' in request[4].imageOptions)&&!('slotWidth' in request[4].imageOptions)));
});
test('failed attempt retains the reference and retries the same empty slot',async()=>{
 const h=harness();h.context.callGenerate=async()=>{throw new Error('provider failed');};await h.context.generateEditWorkspace();
 const slot=h.state.chain[1],position=slot.x;assert.equal(slot.status,'failed');assert.equal(h.state.sourceUrl,h.state.chain[0].url);assert.equal(h.state.history.length,0);
 h.context.callGenerate=async()=>({images:['https://cdn.example/retry.png']});await h.context.generateEditWorkspace();
 assert.equal(h.state.chain.length,2);assert.equal(h.state.chain[1],slot);assert.equal(slot.x,position);assert.equal(slot.status,'ready');
});
test('chain previews inherit predecessor size at every canvas zoom without changing pixel dimensions',()=>{
 const h=harness();
 for(const [width,height,zoom] of [[6000,4000,100],[4000,6000,200],[24000,3000,50],[1200,800,800]]){
  Object.assign(h.state,{width,height,zoom,chain:[],activeNodeId:''});
  const reference=h.context.ensureEditWorkspaceChain(),slot=h.context.beginEditWorkspaceChainResult();
  assert.equal(reference.width,width);assert.equal(reference.height,height);assert.equal(slot.slotWidth,reference.slotWidth);assert.equal(slot.slotHeight,reference.slotHeight);
  assert.equal(h.state.width,width);assert.equal(h.state.height,height);assert.equal(h.state.zoom,zoom);
 }
});
test('visible session history outlives the undo stack limit and Undo does not delete images',async()=>{
 const h=harness();let index=0;h.context.callGenerate=async()=>({images:['https://cdn.example/'+(++index)+'.png']});
 for(let i=0;i<22;i++){h.context.setEditWorkspaceDimensions(1200,800);await h.context.generateEditWorkspace();}
 assert.equal(h.state.chain.length,23);assert.equal(h.state.history.length,20);const last=h.state.chain.at(-1);
 h.context.undoEditWorkspace();assert.equal(h.state.chain.length,23);assert.equal(last.url,'https://cdn.example/22.png');assert.equal(h.state.sourceUrl,'https://cdn.example/21.png');
 assert.equal(h.state.activeNodeId,h.state.chain[21].id);
 h.context.setEditWorkspaceDimensions(1200,800);await h.context.generateEditWorkspace();
 assert.equal(h.state.chain.length,24);assert.equal(h.state.chain.at(-1).parentId,h.state.chain[21].id);
 assert.ok(h.state.chain.at(-1).x-h.state.chain.at(-1).slotWidth/2>last.x+last.slotWidth/2,'new result must not cover retained history after Undo');
});
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
test('Upscale preserves panoramic ratios at edge limits and shows the actual scale',()=>{
 const h=harness();h.state.mode='upscale';h.context.setEditWorkspaceDimensions(8000,1000);h.context.setEditUpscaleScale(null,4);
 assert.equal(h.state.upscale.width,24000);assert.equal(h.state.upscale.height,3000);assert.equal(h.state.upscale.scale,3);
 assert.equal(h.context.editWorkspaceValidation(),'');
 const panel=h.context.editUpscalePanel('',()=> '');assert.match(panel,/24000 × 3000 px · 3×/);assert.doesNotMatch(panel,/aria-pressed="true"/);
 h.context.setEditWorkspaceDimensions(1000,8000);h.context.setEditUpscaleScale(null,4);
 assert.equal(h.state.upscale.width,3000);assert.equal(h.state.upscale.height,24000);
});
test('Upscale caps pixel area without stretching and normalizes either dimension to Topaz rounding',()=>{
 const h=harness();h.state.mode='upscale';
 for(const [w,height] of [[5000,5000],[4031,3023],[12001,317],[317,12001],[3,2]]){
  h.context.setEditWorkspaceDimensions(w,height);h.context.setEditUpscaleScale(null,4);
  const u=h.state.upscale;assert.ok(u.width*u.height<=100000000);assert.ok(Math.max(u.width,u.height)<=24000);
  assert.equal(u.width,Math.max(1,Math.round(w*u.height/height)));assert.equal(h.context.editWorkspaceValidation(),'');
 }
 h.context.setEditWorkspaceDimensions(1200,800);
 h.context.updateEditWorkspaceField({currentTarget:{type:'number',value:'1501'}},'upscale','width');
 assert.equal(h.state.upscale.height,1001);assert.equal(h.state.upscale.width,1502);
 h.context.updateEditWorkspaceField({currentTarget:{type:'number',value:'333'}},'upscale','height');
 assert.equal(h.state.upscale.height,333);assert.equal(h.state.upscale.width,500);assert.equal(h.context.editWorkspaceValidation(),'');
 h.state.upscale.width=499;assert.match(h.context.editWorkspaceValidation(),/пропорции/);
});
test('Upscale rejects corrupt numeric controls and preserves face settings while disabled',()=>{
 const h=harness();h.context.setEditWorkspaceDimensions(1200,800);
 h.context.updateEditWorkspaceRange({currentTarget:{value:'0'}},'upscale','strength');
 h.context.updateEditWorkspaceRange({currentTarget:{value:'101'}},'upscale','denoise');
 assert.equal(h.state.upscale.strength,0);assert.equal(h.state.upscale.denoise,100);
 h.context.updateEditWorkspaceRange({currentTarget:{value:'NaN'}},'upscale','denoise');assert.equal(h.state.upscale.denoise,100);
 h.context.updateEditWorkspaceField({currentTarget:{type:'checkbox',checked:false}},'upscale','faceEnhancement');
 assert.match(h.context.editUpscalePanel('',()=>''),/class="edit-upscale-faces" disabled/);
 h.context.updateEditWorkspaceRange({currentTarget:{value:'80'}},'upscale','strength');assert.equal(h.state.upscale.strength,0);
 h.state.busy=true;const saved=JSON.stringify(h.state.upscale);h.context.setEditUpscaleScale(null,4);
 h.context.updateEditWorkspaceField({currentTarget:{type:'number',value:'800'}},'upscale','width');assert.equal(JSON.stringify(h.state.upscale),saved);
});
test('Upscale sends isolated controls once, keeps camera unchanged, and preserves failed inputs',async()=>{
 const h=harness();h.state.mode='upscale';h.context.setEditWorkspaceDimensions(1200,800);h.context.setEditUpscaleScale(null,4);
 h.state.upscale.faceEnhancement=false;h.state.upscale.sharpness=73;h.state.viewport={x:100,y:-50};h.state.zoom=400;
 const original=JSON.stringify(h.state.upscale);let fail;h.context.callGenerate=async(...args)=>{h.requests.push(args);return new Promise((_,reject)=>{fail=reject;});};
 const pending=h.context.generateEditWorkspace();await h.context.generateEditWorkspace();assert.equal(h.requests.length,1);
 const opts=h.requests[0][4];assert.equal(opts.provider,'topaz');assert.equal(opts.model,'topaz_enhance_photo');assert.equal(opts.isolateRequest,true);
 assert.equal(opts.imageOptions.editWorkspaceUpscale.width,4800);assert.equal(opts.imageOptions.editWorkspaceUpscale.sharpness,73);assert.equal(opts.imageOptions.editWorkspaceUpscale.faceEnhancement,false);
 assert.equal(opts.imageOptions.viewport,undefined);assert.equal(h.state.camera.zoom,5);
 fail(new Error('Topaz unavailable'));await pending;assert.equal(JSON.stringify(h.state.upscale),original);assert.equal(h.state.busy,false);assert.equal(h.state.history.length,0);
});
test('Upscale quotes come from the server; stale responses cannot replace the current size quote',async()=>{
 const h=harness(),quotes=[],node={textContent:''};h.state.mode='upscale';h.context.setEditWorkspaceDimensions(3000,2000);
 h.context.document.querySelector=()=>node;
 h.context.fetch=async(url,options)=>new Promise(resolve=>quotes.push({url,payload:JSON.parse(options.body),resolve}));
 const first=h.context.refreshEditUpscaleEstimate();await h.context.refreshEditUpscaleEstimate();assert.equal(quotes.length,1);
 h.context.setEditUpscaleScale(null,4);const second=h.context.refreshEditUpscaleEstimate();assert.equal(quotes.length,2);
 assert.equal(quotes[1].url,'/api/public/prostudio/estimate');assert.equal(quotes[1].payload.image_options.editWorkspaceUpscale.width,12000);
 assert.deepEqual(quotes[1].payload.image_options.referenceImageUrls,[h.state.sourceUrl]);assert.deepEqual(quotes[1].payload.image_options.referenceImages,[h.state.sourceUrl]);
 quotes[1].resolve({ok:true,json:async()=>({ok:true,credits:75})});await second;assert.equal(node.textContent,'75 ⚡');
 quotes[0].resolve({ok:true,json:async()=>({ok:true,credits:15})});await first;assert.equal(node.textContent,'75 ⚡');
 h.context.setEditUpscaleScale(null,1);h.context.fetch=async()=>{throw new Error('offline');};await h.context.refreshEditUpscaleEstimate();assert.equal(node.textContent,'Уточняется при запуске');
});
test('failed upload preserves existing document and chain; successful upload starts a new reference',async()=>{
 const h=harness();await h.context.generateEditWorkspace();const savedChain=JSON.stringify(h.state.chain),savedUrl=h.state.sourceUrl;
 h.failUpload();await h.context.loadEditWorkspaceImage({name:'new.png',type:'image/png',size:10});
 assert.equal(h.state.sourceUrl,savedUrl);assert.equal(JSON.stringify(h.state.chain),savedChain);assert.equal(h.state.uploading,false);assert.deepEqual(h.revoked,['blob:new']);
 const ok=harness();await ok.context.generateEditWorkspace();ok.state.maskStrokes=[{}];await ok.context.loadEditWorkspaceImage({name:'new.png',type:'image/png',size:10});
 assert.equal(ok.state.sourceUrl,'https://cdn.example/new.png');assert.equal(ok.state.maskStrokes.length,0);assert.equal(ok.state.resize.width,1200);
 assert.equal(ok.state.chain.length,1);assert.equal(ok.state.chain[0].url,ok.state.sourceUrl);assert.equal(ok.state.chain[0].parentId,'');assert.equal(ok.state.activeNodeId,ok.state.chain[0].id);
});
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
 assert.equal(options.provider,'openai');assert.equal(options.model,'gpt_image_2_5_sunburst');
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
 h.context.window={matchMedia:()=>({matches:true}),addEventListener:(type,fn)=>listeners['window:'+type]=fn,removeEventListener:type=>delete listeners['window:'+type]};
 const stage={tabIndex:-1,setAttribute(){},focus(){},classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)},
  setPointerCapture:id=>captured.add(id),hasPointerCapture:id=>captured.has(id),releasePointerCapture:id=>captured.delete(id),
  getBoundingClientRect:()=>({left:0,top:0,width:1400,height:900}),addEventListener:(type,fn)=>listeners[type]=fn,removeEventListener:type=>delete listeners[type]};
 const cleanup=h.context.initEditWorkspaceNavigation(stage);
 const event=(overrides={})=>({pointerId:1,button:0,clientX:300,clientY:200,deltaX:0,deltaY:0,deltaMode:0,target:{closest:()=>null},preventDefault(){},stopPropagation(){},...overrides});
 return {...h,root,stage,listeners,classes,captured,event,cleanup,paints:()=>paints};
}
function expandHarness(){
 const h=harness(),captured=new Set(),listeners={},fields=['width','height','left','right','top','bottom'].map(key=>({dataset:{expandField:key}})),output={};let layouts=0;
 h.state.mode='expand';h.context.ensureEditWorkspaceChain();
 const buttons=Object.fromEntries(['left','right','top','bottom'].map(side=>[side,{dataset:{expandHandle:side},focus(){},setPointerCapture:id=>captured.add(id),hasPointerCapture:id=>captured.has(id),releasePointerCapture:id=>captured.delete(id)}]));
 const root={querySelectorAll:selector=>selector==='[data-expand-handle]'?Object.values(buttons):fields,querySelector:()=>output,_editLayout:()=>layouts++};
 h.context.document.getElementById=id=>id==='editWorkspace'?root:null;
 h.context.window={addEventListener:(type,fn)=>listeners[type]=fn,removeEventListener:type=>delete listeners[type]};
 h.context.initEditExpandHandles(root);
 const event=(overrides={})=>({pointerId:1,button:0,clientX:300,clientY:200,preventDefault(){},stopPropagation(){},...overrides});
 return {...h,root,buttons,fields,output,captured,listeners,event,layouts:()=>layouts};
}
test('Expand edge drags map screen pixels to margins at every zoom without moving or resizing the source',()=>{
 for(const zoom of [25,100,400])for(const side of ['left','right','top','bottom']){
  const h=expandHarness();h.state.zoom=zoom;const original=JSON.stringify({node:h.state.chain[0],viewport:h.state.viewport,width:h.state.width,height:h.state.height});
  const button=h.buttons[side],delta=200*.2*zoom/100*(side==='left'||side==='top'?-1:1);
  button.onpointerdown(h.event());button.onpointermove(h.event(side==='left'||side==='right'?{clientX:300+delta}:{clientY:200+delta}));
  assert.equal(h.state.expand[side],200);assert.equal(Object.values(h.state.expand).reduce((a,b)=>a+b),200);
  assert.equal(JSON.stringify({node:h.state.chain[0],viewport:h.state.viewport,width:h.state.width,height:h.state.height}),original);
  assert.equal(h.fields.find(f=>f.dataset.expandField===side).value,'200');assert.ok(h.layouts()>0);
  assert.equal(h.output.textContent,side==='left'||side==='right'?'1400 × 800 px':'1200 × 1000 px');
  button.onpointerup(h.event());assert.equal(h.captured.size,0);assert.equal(h.root._editExpandDrag,false);h.root._editExpandCleanup();assert.equal(Object.keys(h.listeners).length,0);
 }
});
test('Expand cancellation restores margins, keyboard controls work, and busy/comparison views cannot change them',()=>{
 const h=expandHarness(),button=h.buttons.left;
 button.onpointerdown(h.event());button.onpointermove(h.event({clientX:250}));assert.equal(h.state.expand.left,250);
 button.onpointercancel(h.event());assert.equal(h.state.expand.left,0);assert.equal(h.captured.size,0);
 button.onkeydown(h.event({key:'ArrowLeft'}));assert.equal(h.state.expand.left,10);
 button.onkeydown(h.event({key:'ArrowLeft',shiftKey:true}));assert.equal(h.state.expand.left,110);
 button.onpointerdown(h.event());button.onpointermove(h.event({clientX:200}));button.onkeydown(h.event({key:'Escape'}));assert.equal(h.state.expand.left,110);
 button.onkeydown(h.event({key:'Home'}));assert.equal(h.state.expand.left,0);
 for(const key of ['busy','showBefore']){h.state[key]=true;button.onpointerdown(h.event());button.onkeydown(h.event({key:'ArrowLeft'}));h.context.updateEditExpandField({currentTarget:{value:'1600'}},'width');assert.equal(h.state.expand.left,0);assert.equal(h.captured.size,0);h.state[key]=false;}
});
test('Expand exact dimensions and margins stay synchronized, preserve anchors and enforce provider canvas limits',()=>{
 const h=expandHarness(),set=(key,value)=>h.context.updateEditExpandField({type:'change',currentTarget:{value:String(value)}},key);
 set('width',1600);assert.equal(h.state.expand.left,200);assert.equal(h.state.expand.right,200);
 h.context.resetEditExpand();set('right',200);set('width',1800);assert.equal(h.state.expand.left,0);assert.equal(h.state.expand.right,600);
 set('height',1000);assert.equal(h.state.expand.top,100);assert.equal(h.state.expand.bottom,100);
 set('left',-100);assert.equal(h.state.expand.left,0);set('width',500);assert.equal(h.context.editExpandSize().width,1200);
 set('width','invalid');set('width','');assert.equal(h.context.editExpandSize().width,1200);
 h.context.resetEditExpand();h.context.setEditWorkspaceDimensions(6000,2000);set('right',99999);assert.equal(h.state.expand.right,2192);
 set('bottom',99999);const size=h.context.editExpandSize();assert.ok(size.width*size.height<=16777216);assert.ok(Math.max(size.width,size.height)<=8192);
 assert.ok(Object.values(h.state.expand).every(n=>n>=0&&n<=4096));assert.equal(h.context.editWorkspaceValidation(),'');
});
test('Expand sends exact dragged margins, retains them on failure, clears only after success, and Undo restores them',async()=>{
 const h=expandHarness();h.context.setEditExpandMargin('left',200);h.context.setEditExpandMargin('bottom',100);
 const margins=JSON.stringify(h.state.expand);h.context.callGenerate=async()=>{throw new Error('offline');};await h.context.generateEditWorkspace();assert.equal(JSON.stringify(h.state.expand),margins);
 h.context.callGenerate=async(...args)=>{h.requests.push(args);return {images:['https://cdn.example/expanded.png']};};await h.context.generateEditWorkspace();
 assert.equal(JSON.stringify(h.requests[0][4].imageOptions.editWorkspaceExpand),margins);assert.equal(h.requests[0][2][0],'https://cdn.example/source.png');
 assert.equal(Object.values(h.state.expand).reduce((a,b)=>a+b),0);assert.equal(h.state.chain.length,2);
 h.context.undoEditWorkspace();assert.equal(JSON.stringify(h.state.expand),margins);assert.equal(h.state.width,1200);assert.equal(h.state.sourceUrl,'https://cdn.example/source.png');
});
test('each chain card moves independently at canvas zoom and both attached links follow it',async()=>{
 for(const zoom of [25,100,400]){
  const h=navigationHarness();await h.context.generateEditWorkspace();h.context.setEditWorkspaceDimensions(1200,800);await h.context.generateEditWorkspace();
  h.state.zoom=zoom;const nodes=h.state.chain,old=nodes.map(n=>({x:n.x,y:n.y})),view=JSON.stringify(h.state.viewport),urls=JSON.stringify(nodes.map(n=>n.url));
  const cards=new Map(nodes.map(n=>[n.id,{dataset:{chainNode:n.id},style:{},focus(){},classList:{add(){},remove(){}}}]));
  const paths=new Map(nodes.filter(n=>n.parentId).map(n=>[n.id,{setAttribute(k,v){this[k]=v;}}]));
  h.root.querySelector=selector=>{const id=selector.match(/="([^"]+)"/)?.[1];return selector.includes('data-chain-node')?cards.get(id):paths.get(id);};
  h.root._editChainLayout=()=>h.context.paintEditWorkspaceChain(h.root);
  h.root._editChainLayout();const previousPaths=[...paths.values()].map(p=>p.d);
  const target={closest:selector=>selector==='[data-chain-node]'?cards.get(nodes[1].id):null};
  h.stage.onpointerdown(h.event({target}));h.stage.onpointermove(h.event({clientX:420,clientY:260}));h.stage.onpointerup(h.event());
  assert.equal(nodes[1].x,old[1].x+120/(zoom/100));assert.equal(nodes[1].y,old[1].y+60/(zoom/100));
  assert.equal(nodes[0].x,old[0].x);assert.equal(nodes[2].x,old[2].x);assert.equal(JSON.stringify(h.state.viewport),view);assert.equal(JSON.stringify(nodes.map(n=>n.url)),urls);
  assert.notEqual(paths.get(nodes[1].id).d,previousPaths[0]);assert.notEqual(paths.get(nodes[2].id).d,previousPaths[1]);
  for(const node of nodes.slice(1)){const d=paths.get(node.id).d;assert.equal(d,h.context.editWorkspaceChainPath(nodes.find(n=>n.id===node.parentId),node));}
  h.stage.onkeydown(h.event({target,key:'ArrowDown'}));assert.equal(nodes[1].y,old[1].y+84/(zoom/100));
  h.listeners['document:keydown'](h.event({code:'Space'}));h.stage.onpointerdown(h.event({target}));h.stage.onpointermove(h.event({clientX:310,clientY:220}));h.stage.onpointerup(h.event());
  assert.equal(h.state.viewport.x,10);assert.equal(h.state.viewport.y,20);assert.equal(nodes[1].x,old[1].x+120/(zoom/100));
  h.cleanup();
 }
});
test('new cards append on the right after manual rearrangement and keep their actual source link',async()=>{
 const h=harness();await h.context.generateEditWorkspace();const [source,result]=h.state.chain;
 source.x=1800;source.y=-600;result.x=-400;result.y=300;
 h.context.setEditWorkspaceDimensions(1200,800);await h.context.generateEditWorkspace();const next=h.state.chain.at(-1);
 assert.equal(next.parentId,result.id);assert.ok(next.x-next.slotWidth/2>source.x+source.slotWidth/2);assert.equal(next.y,result.y);
 assert.equal(source.x,1800);assert.equal(source.y,-600);assert.equal(h.requests[1][2][0],result.url);
});
test('connection endpoints follow facing edges when a result is moved around its source',()=>{
 const h=harness(),source={x:0,y:0,slotWidth:240,slotHeight:160};
 for(const [x,y,startX,startY,endX,endY] of [[400,0,126,0,274,0],[-400,0,-126,0,-274,0],[0,300,0,86,0,214],[0,-300,0,-86,0,-214]]){
  const numbers=h.context.editWorkspaceChainPath(source,{...source,x,y}).match(/-?\d+(?:\.\d+)?/g).map(Number);
  assert.deepEqual(numbers.slice(0,2),[startX,startY]);assert.deepEqual(numbers.slice(-2),[endX,endY]);
 }
});
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
 h.cleanup();assert.ok(!h.listeners.wheel);assert.ok(!h.listeners['document:keydown']);assert.ok(!h.listeners['document:keyup']);assert.ok(!h.listeners['window:blur']);
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
 assert.equal(lighting.layers[0].horizontal,217.4);assert.equal(lighting.layers[0].brightness,1.7);assert.equal(options.provider,'openai');assert.equal(options.model,'gpt_image_2_5_sunburst');
 h.context.selectEditWorkspaceLight(null,0);h.context.updateEditLight({brightness:.2});assert.equal(lighting.layers[0].brightness,1.7,'request retains an immutable settings snapshot');
});
test('removing a light preserves remaining settings, and adding after an off source creates an enabled light',()=>{
 const h=harness();h.context.updateEditLight({horizontal:122,color:'#aabbcc'});h.context.addEditWorkspaceLight();h.context.updateEditLight({horizontal:241,color:'#112233'});
 h.context.selectEditWorkspaceLight(null,0);h.context.removeEditWorkspaceLight();
 assert.equal(h.state.light.layers.length,1);assert.equal(h.state.light.layers[0].horizontal,241);assert.equal(h.state.light.active,0);
 h.context.removeEditWorkspaceLight();assert.equal(h.state.light.layers.length,1);
 h.context.toggleEditWorkspaceLight();h.context.addEditWorkspaceLight();assert.equal(h.state.light.layers[1].enabled,true);assert.equal(h.state.light.layers[1].brightness,1);
});

test('touch pinch zooms from blank canvas around the midpoint and releases capture',()=>{
 const h=navigationHarness(),e=changes=>h.event({pointerType:'touch',...changes});
 h.listeners.pointerdown(e({pointerId:1,clientX:600,clientY:450}));
 h.stage.onpointerdown(e({pointerId:1,clientX:600,clientY:450}));
 h.listeners.pointerdown(e({pointerId:2,clientX:800,clientY:450}));
 h.listeners.pointermove(e({pointerId:2,clientX:1000,clientY:450}));
 assert.equal(h.state.zoom,200);assert.equal(h.state.viewport.x,100);assert.equal(h.state.viewport.y,0);
 h.listeners.pointerup(e({pointerId:1}));h.listeners.pointerup(e({pointerId:2}));assert.equal(h.captured.size,0);
 h.cleanup();assert.equal(Object.keys(h.listeners).length,0);
});
test('Safari trackpad gestures zoom, prevent page gestures and leave camera coordinates unchanged',()=>{
 const h=navigationHarness();let prevented=0;const event={clientX:700,clientY:450,preventDefault(){prevented++;}};
 h.listeners.gesturestart(event);h.listeners.gesturechange({...event,scale:1.8});h.listeners.gestureend(event);
 assert.equal(h.state.zoom,180);assert.equal(h.state.camera.zoom,5);assert.equal(prevented,3);h.cleanup();
});
test('standard size resets displayed cards and zoom without changing pixels, connections or positions',async()=>{
 const h=harness();await h.context.generateEditWorkspace();h.state.zoom=300;h.state.chain[0].slotWidth=480;h.state.chain[0].slotHeight=320;
 const positions=JSON.stringify(h.state.chain.map(n=>[n.id,n.parentId,n.x,n.y,n.url,n.width,n.height]));
 h.context.resetEditWorkspaceSize();assert.equal(h.state.zoom,100);assert.ok(h.state.chain.every(n=>Math.max(n.slotWidth,n.slotHeight)===240));
 assert.equal(JSON.stringify(h.state.chain.map(n=>[n.id,n.parentId,n.x,n.y,n.url,n.width,n.height])),positions);
});
function sessionHarness(){
 const h=harness(),local=new Map(),cloud=new Map();let owner='111',offline=false;
 h.context.getTelegramId=()=>owner;h.context.localStorage={getItem:k=>local.get(k)||null,setItem:(k,v)=>local.set(k,v)};
 h.context.fetch=async(url,options={})=>{
  if(offline)throw new Error('offline');
  const id=url.split('/').at(-1),key=owner+':'+id;
  if(options.method==='PUT'){cloud.set(key,JSON.parse(options.body).state);return {ok:true};}
  if(url.includes('?offset='))return {ok:true,json:async()=>({sessions:[],hasMore:false})};
  return {ok:cloud.has(key),json:async()=>({state:cloud.get(key)})};
 };
 return {...h,local,cloud,setOwner:v=>owner=v,setOffline:v=>offline=v};
}
function sharedSidebarHarness(){
 const h=sessionHarness(),elements=new Map();
 const classes=(...initial)=>{const set=new Set(initial);return {contains:name=>set.has(name),add:name=>set.add(name),remove:name=>set.delete(name),toggle:(name,on)=>on?set.add(name):set.delete(name)};};
 const root={dataset:{},attributes:{'aria-modal':'true'},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this.attributes[k];},remove(){elements.delete('editWorkspace');}};
 const links=['/pro-studio.html','/pro-studio.html?mode=grid','/pro-studio.html?tool=edit_workspace'].map((href,i)=>({href,classList:classes(...(i===0?['is-active']:[]))}));
 const originalHistory={innerHTML:'Studio history only'},account={onclick:()=>{}},list={classList:classes('sx-sidebar-history-list')},button={};let inserted=0;
 const sidebar={classList:classes(),querySelector:()=>null,querySelectorAll:()=>links,insertBefore:node=>{elements.set(node.id,node);inserted++;}};
 for(const [id,node] of Object.entries({editWorkspace:root,sxSidebar:sidebar,sxSidebarHistory:originalHistory,sxSidebarAccountBtn:account,editSessionList:list,editSidebarNew:button,editSessionSync:{}}))elements.set(id,node);
 h.context.document.getElementById=id=>elements.get(id)||null;
 h.context.document.createElement=()=>({setAttribute(){},remove(){elements.delete(this.id);}});
 h.context.URL=URL;h.context.location={href:'https://sylvex.ai/pro-studio.html'};
 h.context.S={escapeHtml:s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
 return {...h,root,sidebar,originalHistory,account,list,button,links,elements,inserted:()=>inserted};
}
test('Edit reuses the website sidebar across workspace resets and restores Studio history on close',()=>{
 const h=sharedSidebarHarness(),accountHandler=h.account.onclick;
 const shell={inert:false};h.elements.set('sxStudioShell',shell);
 h.context.mountEditWorkspaceSidebar(h.root);
 assert.equal(shell.inert,true);
 assert.equal(h.root.attributes.role,'region');assert.equal(h.root.attributes['aria-modal'],undefined);
 assert.equal(h.context.editWorkspaceSidebar(),'');assert.equal(h.inserted(),1);
 assert.equal(h.links[2].classList.contains('is-active'),true);assert.equal(h.links[0].classList.contains('is-active'),false);
 h.context.resetEditWorkspaceSurface();h.context.mountEditWorkspaceSidebar(h.root);
 assert.equal(h.inserted(),1);assert.ok(h.elements.has('editSidebarHistory'));
 h.context.closeEditWorkspace();
 assert.equal(shell.inert,false);
 assert.equal(h.elements.has('editSidebarHistory'),false);assert.equal(h.sidebar.classList.contains('has-edit-history'),false);
 assert.equal(h.originalHistory.innerHTML,'Studio history only');assert.equal(h.account.onclick,accountHandler);
 assert.equal(h.links[0].classList.contains('is-active'),true);assert.equal(h.links[2].classList.contains('is-active'),false);
});
test('shared menu shows only Edit sessions, escapes titles and locks workspace switching during generation',async()=>{
 const h=sharedSidebarHarness();await h.context.loadEditSessionHistory();
 h.state.sourceName='<img title="unsafe">';h.context.ensureEditWorkspaceChain();await h.context.saveEditWorkspaceSession();
 assert.match(h.list.innerHTML,/sx-sidebar-history-item/);assert.match(h.list.innerHTML,/aria-current="true"/);
 assert.match(h.list.innerHTML,/&lt;img title=&quot;unsafe&quot;>/);assert.doesNotMatch(h.list.innerHTML,/<img|Studio history only/);
 h.state.busy=true;h.context.renderEditSessionList();assert.equal(h.button.disabled,true);assert.match(h.list.innerHTML,/disabled/);
 h.state.busy=false;h.context.renderEditSessionList();assert.equal(h.button.disabled,false);assert.doesNotMatch(h.list.innerHTML,/disabled/);
 assert.equal(h.originalHistory.innerHTML,'Studio history only');
});
test('new workspace keeps complete prior chain and restoring preserves links, geometry and tool settings',async()=>{
 const h=sessionHarness();await h.context.loadEditSessionHistory();await h.context.generateEditWorkspace();
 const id=h.state.sessionId;h.state.chain[0].x=-870;h.state.chain[1].y=163;h.state.zoom=225;h.state.viewport={x:130,y:-40};h.state.camera.horizontal=225;h.state.light.layers[0].color='#ff8800';h.state.resize.width=777;
 const snapshot=h.context.editSessionSnapshot();await h.context.saveEditWorkspaceSession();h.context.newEditWorkspace();
 assert.notEqual(h.state.sessionId,id);assert.equal(h.state.chain.length,0);
 await h.context.openEditSession(id);
 for(const key of ['chain','zoom','viewport','camera','light','resize'])assert.equal(JSON.stringify(h.state[key]),JSON.stringify(snapshot[key]));
 assert.ok(h.cloud.has('111:'+id));
});
test('history restores locally offline, replaces blob previews, and isolates a different account',async()=>{
 const h=sessionHarness();await h.context.loadEditSessionHistory();h.context.ensureEditWorkspaceChain();h.state.sourcePreview='blob:source';h.state.chain[0].preview='blob:source';h.setOffline(true);
 await h.context.saveEditWorkspaceSession();const id=h.state.sessionId;
 assert.doesNotMatch(h.local.get('sylvex-edit-sessions-v1:111'),/blob:/);
 h.context.newEditWorkspace();await h.context.openEditSession(id);assert.equal(h.state.sourcePreview,'https://cdn.example/source.png');
 h.setOwner('222');await h.context.loadEditSessionHistory();assert.equal(h.state.chain.length,0);assert.notEqual(h.state.sessionId,id);
});
test('reopening an interrupted job polls the saved job and fills the original slot without charging again',async()=>{
 const h=harness();h.context.ensureEditWorkspaceChain();const slot=h.context.beginEditWorkspaceChainResult();slot.jobId='existing-job';let polls=0;
 h.context.waitGeneration=async id=>{assert.equal(id,'existing-job');polls++;return {images:['https://cdn.example/recovered.png']};};
 await h.context.recoverEditSessionJob();assert.equal(polls,1);assert.equal(h.requests.length,0);assert.equal(h.state.chain.length,2);assert.equal(slot.status,'ready');assert.equal(h.state.activeNodeId,slot.id);
});
test('unknown job status keeps the job recoverable; confirmed failure allows retry in the same slot',async()=>{
 const h=harness();h.context.ensureEditWorkspaceChain();const slot=h.context.beginEditWorkspaceChainResult();slot.jobId='existing-job';
 h.context.waitGeneration=async()=>{throw Object.assign(new Error('offline'),{terminalStatus:'unconfirmed'});};
 await h.context.recoverEditSessionJob();assert.equal(slot.status,'pending');assert.equal(slot.jobId,'existing-job');
 h.context.waitGeneration=async()=>{throw Object.assign(new Error('failed'),{terminalStatus:'failed'});};
 await h.context.recoverEditSessionJob();assert.equal(slot.status,'failed');const retry=h.context.beginEditWorkspaceChainResult();assert.equal(retry,slot);assert.equal(retry.jobId,'');
});
