import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../webapp/cabinet.html', import.meta.url), 'utf8');
const main = readFileSync(new URL('../main.py', import.meta.url), 'utf8');

test('Grid planner is a hidden autonomous GPT director instead of a Task model picker', () => {
  assert.match(main, /You are SYLVEX Grid Director\. You are the autonomous production brain/);
  assert.match(main, /video\/film: director, screenwriter, cinematographer, editor and continuity supervisor/);
  assert.match(main, /GRID_PLANNER_MODEL = .*gpt-6-astra/);
  assert.match(main, /planner_model = GRID_PLANNER_MODEL/);
  assert.match(cabinet, /if \(type === 'task'\) return '';/);
  assert.doesNotMatch(cabinet, /task:brief,model:source\.model/);
  assert.match(cabinet, /AI production director/);
});

test('planned references can be uploaded, selected, skipped and mapped by id', () => {
  assert.match(cabinet, /data-grid-upload-reference/);
  assert.match(cabinet, /data-grid-reference-existing/);
  assert.match(cabinet, /data-grid-skip-reference/);
  assert.match(cabinet, /reference_id:referenceId/);
  assert.match(cabinet, /REFERENCE IDENTITY MAP \(mandatory\)/);
});

test('Final Montage is a real node with multi-input payload and recoverable server job', () => {
  assert.match(cabinet, /montage: \{ title:'Final Montage'/);
  assert.match(html, /addStudioGridNode\('montage'\)/);
  assert.match(cabinet, /inputs\.video\?\.values/);
  assert.match(cabinet, /audio_tracks:audioTracks/);
  assert.match(main, /@app\.post\("\/api\/public\/prostudio\/grid\/montage"\)/);
  assert.match(main, /GRID_FINAL_MONTAGE_HEARTBEAT_FAILED/);
});

test('Grid execution keeps stable request ids, versions and dependency scheduling', () => {
  assert.match(cabinet, /client_request_id:node\.request_id\|\|''/);
  assert.match(cabinet, /node\.result_versions\.push\(JSON\.parse\(JSON\.stringify\(output\)\)\)/);
  assert.match(cabinet, /const pending=new Set/);
  assert.match(cabinet, /maxParallel=3/);
  assert.match(cabinet, /parents\.some\(parent=>parent\.status!==['"]COMPLETED['"]\)/);
});

test('Grid projects autosave to private server history and remain mobile', () => {
  assert.match(main, /CREATE TABLE IF NOT EXISTS prostudio_grid_projects/);
  assert.match(cabinet, /scheduleStudioGridCloudSave\(\)/);
  assert.match(cabinet, /loadStudioGridCloudProjects\(\)/);
  assert.match(cabinet, /window\.addEventListener\('pagehide'/);
  assert.match(cabinet, /function studioGridAvailableOnThisScreen\(\) \{\s*return true;/);
});

test('Grid history restores the saved viewport, prefers the cloud project, and protects a new blank project from stale sync', () => {
  assert.match(cabinet, /let studioGridProjectSwitchRevision = 0/);
  assert.match(cabinet, /if\(studioGridAccountOwner\(\)\)try\{const response=await fetch\('\/api\/public\/prostudio\/grid-projects\/'/);
  assert.match(cabinet, /if\(!stored\|\|!Array\.isArray\(stored\.nodes\)\)try\{stored=JSON\.parse\(localStorage\.getItem/);
  assert.doesNotMatch(cabinet, /renderStudioGrid\(\);resetStudioGridView\(\);restoreStudioGridJobs\(\);toast\('Grid project opened'/);
  assert.match(cabinet, /const previous=studioGridSnapshot\(loadStudioGridState\(\)\)/);
  assert.match(cabinet, /if\(studioGridAccountOwner\(\)\)void queueStudioGridCloudSave\(previous\)/);
});

test('Grid image and video results open in in-app viewers', () => {
  assert.match(cabinet, /data-grid-open-result/);
  assert.match(cabinet, /openImageViewer\(event,item\.url\|\|item\.preview_url,urls\)/);
  assert.match(cabinet, /function openStudioGridVideoViewer\(url\)/);
  assert.match(cabinet, /openStudioGridVideoViewer\(node\.output\.url\)/);
  assert.doesNotMatch(cabinet, /if\(event\.target\.closest\('\[data-grid-preview\]'\)\).*window\.open/);
});

test('Grid route and the saved layout survive Grid initialization', () => {
  assert.match(cabinet, /requestedMode === 'grid' \|\| requestedView === 'grid'/);
  assert.match(cabinet, /requestedView=String\(layoutParams\.get\('view'\)\|\|''\)\.toLowerCase\(\)/);
  assert.match(cabinet, /requestedLayout=requestedView==='grid'\?'grid':requestedMode/);
  assert.match(cabinet, /setStudioLayout\(requestedLayout === 'grid' \|\| savedLayout === 'grid' \? 'grid' : 'classic'\)/);
});

test('Grid starts with the intelligent brief instead of the legacy fixed image chain', () => {
  assert.match(cabinet, /title:'New intelligent project'/);
  assert.match(cabinet, /title:'Describe the result'/);
  assert.match(cabinet, /legacyStarter=.*grid_task_1.*grid_text_1.*grid_image_1/);
  assert.match(cabinet, /Build intelligent chain/);
});

test('Grid captures an optional brand name and maps reviewed identity into every generated node', () => {
  assert.match(cabinet, /data-grid-reference-name/);
  assert.match(cabinet, /reference_context:referenceContexts/);
  assert.match(cabinet, /PRODUCTION IDENTITY \(mandatory\)/);
  assert.match(cabinet, /create one original .*stable visual characteristics/);
});

test('Grid passes only the dedicated text result into each planned media node', () => {
  assert.match(cabinet, /created\.filter\(node=>\['image','video','music','voice'\]/);
  assert.match(cabinet, /node\.prompt=''/);
  assert.match(main, /Each shot gets its own finished Text prompt and Video node/);
  assert.match(main, /grid_requested_duration_seconds/);
  assert.match(main, /planner_video_duration_mismatch/);
});

test('Grid supports arbitrary parallel comparisons and never substitutes a local template', () => {
  assert.match(main, /A request to compare N generators must produce one fair shared prompt and N parallel media nodes/);
  assert.match(main, /No local\/template plan is permitted/);
  assert.match(main, /planner_temporarily_unavailable/);
  assert.doesNotMatch(main, /def grid_local_fallback_plan/);
});

test('Task references keep explicit ids and flow into GPT-planned nodes', () => {
  assert.match(cabinet, /item\.reference_id=`task_upload_\$\{node\.attachments\.length\+1\}`/);
  assert.match(cabinet, /if\(!item\.reference_id\)item\.reference_id=`task_upload_\$\{index\+1\}`/);
  assert.match(main, /Reuse their exact reference_id on every relevant node/);
});

test('managed Grid director uses Structured Outputs and priced GPT models', () => {
  assert.match(main, /"gpt-6-astra": \("10\.00", "50\.00"\)/);
  assert.match(main, /"gpt-6\.1-sol": \("2\.00", "10\.00"\)/);
  assert.match(main, /"_response_format": grid_plan_response_format\(\)/);
  assert.match(main, /request_payload\["text"\] = \{"format": response_format\}/);
  assert.match(main, /request_payload\.update\(\{"background": True, "store": False\}\)/);
  assert.match(main, /OPENAI_BACKGROUND_RESPONSE/);
  assert.match(main, /GRID_PLANNER_POLL_SAFETY_LIMIT_SECONDS/);
  assert.match(main, /300, min\(600, int\(os\.getenv\("GRID_PLANNER_POLL_SAFETY_LIMIT_SECONDS"\) or 600\)\)/);
  assert.doesNotMatch(main, /GRID_PLANNER_PRIMARY_POLL_TIMEOUT_SECONDS/);
  assert.doesNotMatch(main, /GRID_PLANNER_FALLBACK_POLL_TIMEOUT_SECONDS/);
});

test('Grid catalog exposes and enforces official reference capabilities', () => {
  assert.match(main, /"character_reference": bool\(features\.get\("character"\)\)/);
  assert.match(main, /"object_reference": bool\(features\.get\("object"\)\)/);
  assert.match(main, /planner_image_reference_unsupported/);
  assert.match(main, /planner_video_reference_unsupported/);
});
