import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const cabinet = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('../webapp/cabinet.html', import.meta.url), 'utf8');
const main = readFileSync(new URL('../main.py', import.meta.url), 'utf8');

test('Grid planner is professional, universal and uses the selected text model', () => {
  assert.match(main, /You are SYLVEX Grid Director, a strict professional production orchestrator/);
  assert.match(main, /video\/film: director, screenwriter, cinematographer, editor and continuity supervisor/);
  assert.match(main, /Never use a fixed shot count/);
  assert.match(cabinet, /model:source\.model\|\|gridDefaultModel\('text'\)/);
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

test('Grid route and the saved layout survive Grid initialization', () => {
  assert.match(cabinet, /const requestedLayout = String\(new URLSearchParams\(window\.location\.search \|\| ''\)\.get\('mode'\) \|\| ''\)\.toLowerCase\(\)/);
  assert.match(cabinet, /setStudioLayout\(requestedLayout === 'grid' \|\| savedLayout === 'grid' \? 'grid' : 'classic'\)/);
});
