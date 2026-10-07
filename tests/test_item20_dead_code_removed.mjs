// Run with: node --test tests/test_item20_dead_code_removed.mjs
//
// Regression test for remediation item #20: removal of audit-confirmed
// dead JavaScript code from webapp/js/cabinet.js.
//
// Each symbol below was verified (grep across the whole repo, not just
// cabinet.js) to have zero callers/references beyond its own
// declaration before being deleted:
//   - renderBrandGeneratorHeader() / filterBrandGeneratorHistory(): no
//     call site anywhere (not even a stale onclick reference).
//   - readableColor(): no call site; contrastColor() (which it wrapped)
//     is the one actually used elsewhere and stays.
//   - insertVoiceEditorMarkup(): no call site; replaceVoiceEditorSelection()
//     (which it wrapped) has other live callers and stays.
//   - getGridDownstreamNodes(): no call site; markStudioGridDownstreamStale()
//     is the function Grid Mode actually uses for downstream invalidation
//     and stays.
//   - waitCharacterCreationJob() / waitObjectCreationJob(): thin
//     passthrough wrappers around pollCharacterCreationJob()/
//     pollObjectCreationJob() with no remaining call site - every real
//     caller (startCharacterCreationCardPoll/startObjectCreationCardPoll)
//     already calls the poll* function directly.
//   - Unused constants KLING_VIDEO_DURATIONS, MODEL_ICON_SVG,
//     VIDEO_TEMPLATE_INTRO_KEY, VOICE_STYLE_RU: declared, never read.
//
// This file asserts the dead symbols are gone AND that every protected/
// live symbol named in the remediation boundaries (legacy HeyGen data
// fields, the live poll*/KLING_VIDEO_* siblings, contrastColor,
// markStudioGridDownstreamStale) is still present, so a future accidental
// re-introduction or over-deletion is caught either way.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('../webapp/js/cabinet.js', import.meta.url), 'utf8');

const REMOVED_JS_SYMBOLS = [
  'renderBrandGeneratorHeader',
  'filterBrandGeneratorHistory',
  'readableColor',
  'insertVoiceEditorMarkup',
  'getGridDownstreamNodes',
  'waitCharacterCreationJob',
  'waitObjectCreationJob',
  'KLING_VIDEO_DURATIONS',
  'MODEL_ICON_SVG',
  'VIDEO_TEMPLATE_INTRO_KEY',
  'VOICE_STYLE_RU',
];

const PROTECTED_LIVE_SYMBOLS = [
  'heygenPhotoAvatarId',
  'heygenAvatarGroupId',
  'pollCharacterCreationJob',
  'pollObjectCreationJob',
  'startCharacterCreationCardPoll',
  'startObjectCreationCardPoll',
  'contrastColor',
  'replaceVoiceEditorSelection',
  'markStudioGridDownstreamStale',
  'KLING_VIDEO_BASE_RATIOS',
  'KLING_VIDEO_LONG_DURATIONS',
];

function wordBoundaryCount(name) {
  const pattern = new RegExp(`\\b${name}\\b`, 'g');
  return (source.match(pattern) || []).length;
}

test('every audit-confirmed dead JS symbol has zero remaining occurrences', () => {
  for (const name of REMOVED_JS_SYMBOLS) {
    assert.equal(wordBoundaryCount(name), 0, `${name} was supposed to be removed as dead code`);
  }
});

test('every protected/live JS symbol named in the remediation boundaries is still present', () => {
  for (const name of PROTECTED_LIVE_SYMBOLS) {
    assert.ok(wordBoundaryCount(name) > 0, `${name} must not have been removed`);
  }
});

test('cabinet.js still parses as valid JavaScript after the removals', () => {
  // A syntax error would throw here.
  new Function(source);
});
