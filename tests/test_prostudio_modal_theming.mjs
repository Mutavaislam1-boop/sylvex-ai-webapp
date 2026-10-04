// Run with: node --test tests/test_prostudio_modal_theming.mjs
//
// Regression tests for "Pro Studio Mini App - Navigation + Modal UI
// Cleanup", item 5: every modal/popup opened inside Pro Studio must follow
// the selected Pro Studio theme (Black/Gray/White), not a hardcoded color
// or the unrelated global site light/dark theme.
//
// Root cause this covers: Photo Tool/Photo Catalog/quick-image-detail
// modals and the Character/Object create+picker dialog and resource-delete
// confirm popup are all reparented to document.body by their own open
// logic (confirmed in cabinet.js), so they can only ever inherit Pro
// Studio's --st-* theme tokens via the explicit mirror onto <html>
// (syncStudioThemeVarsToDocument) - never from being a descendant of
// .studio. Any rule on these dialogs that reads --surface/--border/--text
// (the separate, unrelated global site theme) or a bare hex color instead
// of --st-* will visually ignore the Pro Studio theme toggle.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const css = readFileSync(new URL('../webapp/css/cabinet.css', import.meta.url), 'utf8');

function ruleBody(selector) {
  const pattern = new RegExp(selector.replace(/[.#]/g, '\\$&').replace(/\\\./g, '\\.') + '\\{([^}]*)\\}');
  const match = pattern.exec(css);
  assert.ok(match, `rule not found: ${selector}`);
  return match[1];
}

test('the shared Photo Tool/Catalog/quick-image-detail dialog surface reads Pro Studio theme tokens', () => {
  const dialog = ruleBody('.photo-tool-dialog');
  assert.match(dialog, /background:var\(--st-bg-2,/);
  assert.match(dialog, /border:1px solid var\(--st-border,/);
  assert.match(dialog, /color:var\(--st-text,/);
});

test('the Photo Tool dialog header and close button follow the theme too', () => {
  assert.match(ruleBody('.photo-tool-head>button'), /background:var\(--st-bg,/);
  assert.match(ruleBody('.photo-tool-head>button'), /color:var\(--st-text,/);
  assert.match(ruleBody('.photo-tool-head h3'), /color:var\(--st-text,/);
});

test('Character/Object create dialog surface follows the Pro Studio theme, not a fixed dark color', () => {
  const card = ruleBody('.visual-create-card');
  assert.match(card, /background:var\(--st-bg-2,\s*#202020\)/);
  const modal = ruleBody('.visual-create-modal');
  assert.match(modal, /color:var\(--st-text,/);
  const field = ruleBody('.visual-field input,.visual-field select,.visual-field textarea');
  assert.match(field, /background:var\(--st-bg-3,/);
  assert.match(field, /color:var\(--st-text,/);
});

test('Character/Object create Save button uses the Pro Studio accent token', () => {
  assert.match(ruleBody('.visual-create-save'), /background:var\(--st-accent,/);
});

test('the resource-delete confirm popup (Character/Object/Voice delete) follows the Pro Studio theme', () => {
  const card = ruleBody('.resource-delete-confirm-card');
  assert.match(card, /background:var\(--st-bg-2,/);
  assert.match(card, /border:1px solid var\(--st-border,/);
  assert.match(ruleBody('.resource-delete-confirm-title'), /color:var\(--st-text,/);
  assert.match(ruleBody('.resource-delete-action'), /background:var\(--st-accent,/);
});

test('fallback values exactly preserve the previous hardcoded appearance (no visual change where --st-* is unavailable)', () => {
  assert.match(ruleBody('.photo-tool-dialog'), /var\(--st-bg-2, var\(--surface-2\)\)/);
  assert.match(ruleBody('.visual-create-card'), /var\(--st-bg-2, #202020\)/);
  assert.match(ruleBody('.resource-delete-confirm-card'), /var\(--st-bg-2, #202020\)/);
});
