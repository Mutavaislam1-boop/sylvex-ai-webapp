import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../webapp/js/cabinet.js',import.meta.url),'utf8');
const css=readFileSync(new URL('../webapp/css/cabinet.css',import.meta.url),'utf8');

function extractFunction(name){
  const match=new RegExp(`^([ \\t]*)(?:async )?function ${name}\\(`,'m').exec(source);
  assert.ok(match,`declaration not found: ${name}`);
  const open=source.indexOf('{',match.index);let depth=0,index=open;
  for(;index<source.length;index++){if(source[index]==='{')depth++;else if(source[index]==='}'){depth--;if(depth===0)break}}
  return source.slice(match.index,index+1);
}

test('Sylvex Restore remains inside Edit Upscale while Enhance Photo modal stays Topaz',()=>{
  assert.ok(source.includes("SYLVEX.setEditUpscaleModel(event,\\'topaz\\')"));
  assert.ok(source.includes("SYLVEX.setEditUpscaleModel(event,\\'sylvex_sr\\')"));
  assert.match(source,/tool:'edit_workspace',editWorkspaceMode:mode/);
  assert.match(source,/enhancePhotoModel:'sylvex_sr'/);
  const enhance=extractFunction('generateEnhancePhotoTool');
  assert.match(enhance,/model: 'topaz_enhance_photo'/);
  assert.doesNotMatch(enhance,/sylvex_sr|Sylvex Restore/);
});

test('manual workflow has no automatic analysis gate',()=>{
  assert.doesNotMatch(source,/\/api\/public\/enhance\/sylvex-sr\/analyze/);
  assert.doesNotMatch(source,/Start with analysis|Apply Auto|Analyzing important uncertain regions/);
  assert.match(source,/Select area/);
  assert.match(source,/Generate immediately for full-photo restoration/);
  const validation=extractFunction('editWorkspaceValidation');
  assert.doesNotMatch(validation,/analysisStatus|Analyze the current image/);
});

test('manual regions render movable reference blocks with flexible connections',()=>{
  assert.match(source,/function editSylvexGuidePath/);
  assert.match(source,/data-sr-guide/);
  assert.match(source,/guideX/);
  assert.match(source,/guideX=active\.x-active\.slotWidth\/2-78/);
  assert.match(source,/animateEditSylvexGuidesIntoSource/);
  assert.match(css,/\.edit-sr-guide-line/);
  assert.match(css,/\.edit-sr-reference-node/);
  assert.match(css,/@keyframes edit-sr-line-in/);
});

test('client allows empty plans and enforces four photo references',()=>{
  const context=vm.createContext({});vm.runInContext(extractFunction('validateSylvexRestorePlan'),context);
  assert.equal(context.validateSylvexRestorePlan({regions:[]}),'');
  assert.equal(context.validateSylvexRestorePlan({regions:Array.from({length:4},(_,index)=>({region_id:`region_${index+1}`,reference_asset_id:`ref-${index}`}))}),'');
  assert.match(context.validateSylvexRestorePlan({regions:Array.from({length:5},(_,index)=>({region_id:`region_${index+1}`,reference_asset_id:`ref-${index}`}))}),/up to 4 photo references/);
});

test('request preserves explicit region mapping and exact X1 X2 X4 setting',()=>{
  assert.match(source,/sylvexRestoreRegions:serializeSylvexRestoreRegions\(restore\.regions\)/);
  assert.match(source,/sylvexRestoreFinalEnhance:\{\.\.\.restore\.finalEnhance\}/);
  assert.doesNotMatch(source,/sylvexRestoreAnalysisId|sylvexRestoreRetryRegionIds|sylvexRestoreFinalOnly/);
  assert.match(extractFunction('setEditUpscaleScale'),/\[1,2,4\]/);
  assert.match(extractFunction('setEditUpscaleScale'),/width:s\.width\*scale,height:s\.height\*scale,scale/);
  assert.match(extractFunction('setEditUpscaleScale'),/upscale_factor=scale/);
});
