// =====================================================
// АВТОДОКУМЕНТАЦИЯ SYLVEX: webapp/js/elevenlabs.js
// Файл содержит frontend-логику Mini App.
// Комментарии описывают экраны, кнопки, запросы и обработчики без изменения поведения.
// =====================================================
(function () {
  const S = window.SYLVEX || {};
  const tg = S.tg || window.Telegram && window.Telegram.WebApp;

  const state = {
    telegramId: 0,
    voices: [],
    models: [],
    settings: {}
  };

  const els = {};

  // =====================================================
  // JAVASCRIPT-БЛОК: toast
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function toast(message) {
    if (typeof window.toast === 'function') {
      window.toast(message);
      return;
    }

    const node = document.getElementById('toast');
    if (!node) return;
    node.textContent = message;
    node.classList.add('show');
    setTimeout(() => node.classList.remove('show'), 2600);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: getTelegramUser
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function getTelegramUser() {
    const unsafe = tg && tg.initDataUnsafe || {};
    return unsafe.user || {};
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: option
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function option(value, label, selected) {
    return '<option value="' + String(value || '').replace(/"/g, '&quot;') + '"' + (selected ? ' selected' : '') + '>' + label + '</option>';
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: voiceMatchesType
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function voiceMatchesType(voice, type) {
    if (!type || type === 'all') return true;
    const gender = String(voice.gender || '').trim().toLowerCase();
    const category = String(voice.category || '').trim().toLowerCase();
    const name = String(voice.name || '').trim().toLowerCase();
    const language = String(voice.language || '').trim().toLowerCase();
    const words = [
      name,
      category,
      gender,
      language
    ].join(' ').split(/[^a-zа-яё]+/i).filter(Boolean);
    const text = [
      voice.name || '',
      voice.category || '',
      voice.gender || '',
      voice.language || ''
    ].join(' ').toLowerCase();

    if (type === 'male') return gender === 'male' || words.includes('male') || words.includes('man');
    if (type === 'female') return gender === 'female' || words.includes('female') || words.includes('woman');
    if (type === 'narration') return text.includes('narrat') || text.includes('news') || text.includes('professional');
    if (type === 'character') return text.includes('character') || text.includes('cartoon') || text.includes('animated') || text.includes('anime');
    return true;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: filteredVoices
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function filteredVoices() {
    const type = els.voiceTypeSelect.value;
    const selectedVoice = els.voiceSelect.value || state.settings.voice_id;
    // =====================================================
    // JAVASCRIPT-БЛОК: voices
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const voices = state.voices.filter(voice => voiceMatchesType(voice, type));
    if (voices.length) return voices;
    if (selectedVoice) {
      // =====================================================
      // JAVASCRIPT-БЛОК: current
      // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
      // =====================================================
      const current = state.voices.find(voice => voice.voice_id === selectedVoice);
      if (current) return [current];
    }
    return state.voices;
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderModels
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderModels() {
    const current = state.settings.model_id || 'eleven_multilingual_v2';
    els.modelSelect.innerHTML = state.models.map(model => {
      return option(model.model_id, model.name || model.model_id, model.model_id === current);
    }).join('');
  }

  // =====================================================
  // ОТРИСОВКА ИНТЕРФЕЙСА: renderVoices
  // Обновляет HTML на экране: карточки, списки, previews, историю или состояние кнопок.
  // =====================================================
  function renderVoices() {
    const current = state.settings.voice_id || '21m00Tcm4TlvDq8ikWAM';
    const voices = filteredVoices();
    els.voiceSelect.innerHTML = voices.map(voice => {
      const meta = [voice.gender, voice.language].filter(Boolean).join(' · ');
      const label = voice.name + (meta ? ' — ' + meta : '');
      return option(voice.voice_id, label, voice.voice_id === current);
    }).join('');
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: setSlider
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function setSlider(input, label, value) {
    input.value = value;
    label.textContent = Number(value).toFixed(2);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: applySettings
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function applySettings(settings) {
    state.settings = settings || {};
    renderModels();
    els.voiceTypeSelect.value = 'all';
    renderVoices();
    els.languageSelect.value = state.settings.language || 'ru';
    setSlider(els.stabilityInput, els.stabilityValue, state.settings.stability ?? 0.5);
    setSlider(els.similarityInput, els.similarityValue, state.settings.similarity_boost ?? 0.75);
    setSlider(els.styleInput, els.styleValue, state.settings.style ?? 0);
    setSlider(els.speedInput, els.speedValue, state.settings.speed ?? 1);
    els.speakerBoostInput.checked = state.settings.speaker_boost !== false;
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: collectSettings
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function collectSettings() {
    // =====================================================
    // JAVASCRIPT-БЛОК: voice
    // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
    // =====================================================
    const voice = state.voices.find(item => item.voice_id === els.voiceSelect.value) || {};
    return {
      telegram_id: state.telegramId,
      voice_id: els.voiceSelect.value,
      voice_name: voice.name || 'Voice',
      model_id: els.modelSelect.value,
      stability: Number(els.stabilityInput.value),
      similarity_boost: Number(els.similarityInput.value),
      style: Number(els.styleInput.value),
      speed: Number(els.speedInput.value),
      speaker_boost: els.speakerBoostInput.checked,
      language: els.languageSelect.value,
      output_format: 'mp3_44100_128'
    };
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: loadBootstrap
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function loadBootstrap() {
    const user = getTelegramUser();
    state.telegramId = Number(user.id || new URLSearchParams(location.search).get('telegram_id') || 0);

    const response = await fetch('/api/elevenlabs/bootstrap?telegram_id=' + encodeURIComponent(state.telegramId));
    const data = await response.json();
    if (!data.success) throw new Error(data.error || 'Unable to load settings');

    state.voices = data.voices || [];
    state.models = data.models || [];
    applySettings(data.settings || data.defaults || {});

    if (data.warnings && data.warnings.length) {
      console.warn('ELEVENLABS BOOTSTRAP WARNINGS', data.warnings);
      toast('ElevenLabs API требует проверки ключа и прав доступа.');
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: save
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function save() {
    if (!state.telegramId) {
      toast('Откройте страницу из Telegram Mini App');
      return;
    }

    els.saveButton.disabled = true;
    els.saveButton.textContent = 'Сохраняется...';

    try {
      const settingsPayload = collectSettings();
      console.log('ELEVENLABS SETTINGS FRONTEND SAVE', {
        telegram_id: settingsPayload.telegram_id,
        voice_id: settingsPayload.voice_id,
        voice_name: settingsPayload.voice_name,
        model_id: settingsPayload.model_id,
        stability: settingsPayload.stability,
        similarity_boost: settingsPayload.similarity_boost,
        style: settingsPayload.style,
        speed: settingsPayload.speed,
        speaker_boost: settingsPayload.speaker_boost,
        language: settingsPayload.language
      });

      const response = await fetch('/api/elevenlabs/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsPayload)
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Save failed');
      toast('Настройки сохранены');
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
      if (tg && typeof tg.close === 'function') {
        setTimeout(() => tg.close(), 900);
      }
    } catch (error) {
      toast('Не удалось сохранить настройки');
      console.error(error);
    } finally {
      els.saveButton.disabled = false;
      els.saveButton.textContent = 'Сохранить';
    }
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: bind
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  function bind() {
    els.modelSelect = document.getElementById('modelSelect');
    els.voiceTypeSelect = document.getElementById('voiceTypeSelect');
    els.voiceSelect = document.getElementById('voiceSelect');
    els.languageSelect = document.getElementById('languageSelect');
    els.stabilityInput = document.getElementById('stabilityInput');
    els.similarityInput = document.getElementById('similarityInput');
    els.styleInput = document.getElementById('styleInput');
    els.speedInput = document.getElementById('speedInput');
    els.speakerBoostInput = document.getElementById('speakerBoostInput');
    els.stabilityValue = document.getElementById('stabilityValue');
    els.similarityValue = document.getElementById('similarityValue');
    els.styleValue = document.getElementById('styleValue');
    els.speedValue = document.getElementById('speedValue');
    els.saveButton = document.getElementById('saveButton');

    // =====================================================
    // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
    // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
    // =====================================================
    els.voiceTypeSelect.addEventListener('change', renderVoices);
    [
      [els.stabilityInput, els.stabilityValue],
      [els.similarityInput, els.similarityValue],
      [els.styleInput, els.styleValue],
      [els.speedInput, els.speedValue]
    ].forEach(([input, label]) => {
      input.addEventListener('input', () => {
        label.textContent = Number(input.value).toFixed(2);
      });
    });
    // =====================================================
    // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
    // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
    // =====================================================
    els.saveButton.addEventListener('click', save);
  }

  // =====================================================
  // JAVASCRIPT-БЛОК: init
  // Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend.
  // =====================================================
  async function init() {
    if (tg) {
      try {
        tg.ready();
        tg.expand();
      } catch (e) {}
    }

    bind();
    try {
      await loadBootstrap();
    } catch (error) {
      toast('Не удалось загрузить ElevenLabs');
      console.error(error);
      applySettings({
        voice_id: '21m00Tcm4TlvDq8ikWAM',
        voice_name: 'Rachel',
        model_id: 'eleven_multilingual_v2',
        stability: 0.5,
        similarity_boost: 0.75,
        style: 0,
        speed: 1,
        speaker_boost: true,
        language: 'ru'
      });
    }
  }

  // =====================================================
  // ОБРАБОТЧИК СОБЫТИЯ БРАУЗЕРА
  // Связывает действие пользователя или загрузку страницы с нужной функцией интерфейса.
  // =====================================================
  document.addEventListener('DOMContentLoaded', init);
})();
