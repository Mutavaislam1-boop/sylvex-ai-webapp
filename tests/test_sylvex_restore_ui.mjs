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

test('Sylvex Restore is exposed in Edit Upscale beside the infinite canvas',()=>{
  assert.ok(source.includes("SYLVEX.setEditUpscaleModel(event,\\'topaz\\')"));
  assert.ok(source.includes("SYLVEX.setEditUpscaleModel(event,\\'sylvex_sr\\')"));
  assert.match(source,/tool:'edit_workspace',editWorkspaceMode:mode/);
  assert.match(source,/enhancePhotoModel:'sylvex_sr'/);
  assert.match(source,/initEditSylvexRestoreOverlay\(\)/);
  const photoToolRenderer=extractFunction('renderEnhancePhotoModal');
  assert.match(photoToolRenderer,/renderTopazEnhanceBody\(state\)/);
  assert.doesNotMatch(photoToolRenderer,/enhancePhotoModelSelectorHtml/);
});

test('guided UI includes all required actions, manual regions and protection modes',()=>{
  for(const label of ['Auto Restore','Upload Reference','Enter Text','Protect Region','Skip','Add Region','Apply Auto','Hard Protect','Soft Protect'])assert.ok(source.includes(label),label);
  assert.match(css,/\.edit-sr-region/);
  assert.match(css,/\.edit-sr-draft/);
});

test('client plan validation blocks missing explicit region guidance',()=>{
  const context=vm.createContext({});vm.runInContext(extractFunction('validateSylvexRestorePlan'),context);
  const missingReference={regions:[{region_id:'region_1',user_action:'upload_reference',reference_asset_id:null}]};
  assert.match(context.validateSylvexRestorePlan(missingReference),/reference image/);
  const missingText={regions:[{region_id:'region_2',user_action:'enter_text',text_instruction:''}]};
  assert.match(context.validateSylvexRestorePlan(missingText),/text instruction/);
  const valid={regions:[{region_id:'region_3',user_action:'protect_region',protection_mode:'hard'}]};
  assert.equal(context.validateSylvexRestorePlan(valid),'');
});

test('restore request keeps explicit region IDs and retry controls',()=>{
  assert.match(source,/sylvexRestoreRegions:serializeSylvexRestoreRegions\(restore\.regions\)/);
  assert.match(source,/sylvexRestoreRetryRegionIds/);
  assert.match(source,/sylvexRestoreFinalOnly/);
  assert.match(source,/Retry this region/);
  assert.match(source,/Retry final enhancement/);
});
