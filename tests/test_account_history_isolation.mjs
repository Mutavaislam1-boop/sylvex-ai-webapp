import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const cabinet=readFileSync(new URL('../webapp/js/cabinet.js',import.meta.url),'utf8');

test('Grid local history is namespaced by the authenticated account',()=>{
  assert.match(cabinet,/const STUDIO_GRID_LOCAL_PREFIX = 'sylvex-prostudio-grid-v3:'/);
  assert.match(cabinet,/STUDIO_GRID_LOCAL_PREFIX\+studioGridStorageOwner\+':active'/);
  assert.match(cabinet,/STUDIO_GRID_LOCAL_PREFIX\+studioGridStorageOwner\+':projects'/);
  assert.match(cabinet,/STUDIO_GRID_LOCAL_PREFIX\+studioGridStorageOwner\+':project:'/);
  assert.doesNotMatch(cabinet,/localStorage\.getItem\('sylvex-prostudio-grid-v1'/);
  assert.doesNotMatch(cabinet,/const STUDIO_GRID_PROJECTS_KEY/);
});

test('website auth boot uses a non-persistent pending namespace',()=>{
  assert.match(cabinet,/usesWebSessionAuth\(\)\) return 'pending'/);
  assert.match(cabinet,/activateProStudioAccountOwner\(owner\)/);
  assert.match(cabinet,/if \(Number\(getTelegramId\(\)\) !== Number\(tg\)\) return/);
});

test('Edit does not copy guest drafts into a newly authenticated owner',()=>{
  assert.match(cabinet,/A guest\/pending workspace has no verified owner/);
  assert.doesNotMatch(cabinet,/guestDrafts\.forEach/);
  assert.match(cabinet,/if\(previousOwner\)\{resetEditWorkspaceSurface\(\);Object\.assign\(editWorkspaceState,createEditWorkspaceState\(\)\);\}/);
});

test('stale Grid cloud responses cannot populate a newer account',()=>{
  assert.match(cabinet,/if\(owner!==studioGridAccountOwner\(\)\|\|loadRevision!==studioGridProjectSwitchRevision\)return/);
});
