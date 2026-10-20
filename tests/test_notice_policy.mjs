// Run with: node --test tests/test_notice_policy.mjs
//
// Notices show only when a photo is added, on an error, and when a
// generation finishes or fails. Mode switches, selections, copies, saves,
// deletes, payment progress and other confirmations are silent, and the
// same notice is never repeated while it is still shown.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const read = (path) => readFileSync(new URL('../' + path, import.meta.url), 'utf8');
const cabinet = read('webapp/js/cabinet.js');

test('no notice on mode switches, selections, copies or other confirmations', () => {
  assert.ok(!/const labels = \{ image:'Generate Image'/.test(cabinet), 'genAction no longer announces the mode');
  for (const gone of ["'Generate Voiceover'", "'Персонаж выбран'", "'Текст скопирован'", "'Ссылка скопирована'", "'Выбор очищен'", "'Шаблон применён'",
    "'Ссылка добавлена'", "'Загружаем видео…'", "'Создаём счёт…'", "'Оплата получена, начисляем…'", "'Голос удалён'", "'Трек сохранён'",
    "'Grid project opened'", "'Связь удалена'", "'Текст сохранён'", 'label'])
    assert.ok(!cabinet.includes('toast(' + gone + ')'), gone);
  assert.ok(!read('webapp/js/language.js').includes('window.toast(LANG_META[L].name)'));
  assert.ok(!read('webapp/js/account-auth.js').includes("toast('Signed in')"));
});

test('photos added, errors and generation results still notify', () => {
  assert.ok(cabinet.includes("toast('Фото добавлено')"));
  assert.ok(cabinet.includes("unlockAfterRender = true;\n      toast('Генерация завершена');"), 'sendChat success');
  assert.ok(cabinet.includes("chatMessages.push(resolveFailureMessage(err, { prompt: v }));\n      toast('Ошибка генерации');"), 'sendChat failure');
  assert.ok(cabinet.includes("      loadConversations();\n      toast('Генерация завершена');\n    } catch (err) {\n      if (!(err && err.subscriptionRequired)) toast('Ошибка генерации');"), 'text generation');
  assert.ok(cabinet.includes("clearActiveProStudioJob(activeGeneration.jobId);\n    toast('Генерация завершена');"), 'restored background job');
  assert.ok(cabinet.includes("editWorkspaceToast('Генерация завершена');"), 'Edit workspace');
  assert.ok(cabinet.includes("toast('Недостаточно токенов')"));
});

test('the same notice is not repeated while it is shown', () => {
  const main = read('swipe_toast/src/main.jsx');
  assert.ok(main.includes('list.some(item => item.title === toast.title && item.description === toast.description)\n          ? list'));
});
