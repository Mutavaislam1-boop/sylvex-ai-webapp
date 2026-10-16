// Run with: node --test tests/test_video_editor_transitions.mjs
import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as T from '../webapp/js/video-editor/transitions.js';

test('the SYLVEX library is engine-neutral and filtered by what the engine draws', () => {
  const ids = new Set(T.TRANSITIONS.map((item) => item.id));
  assert.equal(ids.size, T.TRANSITIONS.length);
  assert.ok(T.TRANSITIONS.length > 20);
  assert.deepEqual(T.availableTransitions(['cross-fade', 'push']).map((item) => item.id), ['cross-fade', 'push-left', 'push-right', 'push-up', 'push-down']);
  assert.deepEqual(T.availableTransitions([]), []);
});

test('older projects that stored bare engine types still resolve', () => {
  assert.equal(T.transitionById('push').id, 'push-left');
  assert.equal(T.transitionById('cross-fade').kind, 'cross-fade');
  assert.equal(T.transitionById('unknown'), null);
});

test('previews are small animated markup with the neighbouring frames', () => {
  const html = T.transitionPreview(T.transitionById('wipe-up'), {url: 'data:a', key: 'm@1.00'}, {});
  assert.match(html, /ve-tp-wipe ve-tp-up/);
  assert.match(html, /data-frame="m@1.00"/);
  assert.match(html, /url\(&quot;data:a&quot;\)/);
});
