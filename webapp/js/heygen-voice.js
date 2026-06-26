(function () {
  const S = window.SYLVEX || {};
  const tg = S.tg || window.Telegram && window.Telegram.WebApp;

  const state = {
    telegramId: 0,
    voices: [],
    settings: {}
  };

  const els = {};

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

  function getTelegramUser() {
    const unsafe = tg && tg.initDataUnsafe || {};
    return unsafe.user || {};
  }

  function escapeValue(value) {
    return String(value || '').replace(/"/g, '&quot;');
  }

  function option(value, label, selected) {
    return '<option value="' + escapeValue(value) + '"' + (selected ? ' selected' : '') + '>' + label + '</option>';
  }

  function voiceMatchesType(voice, type) {
    if (!type || type === 'all') return true;
    const gender = String(voice.gender || '').trim().toLowerCase();
    if (type === 'male') return gender === 'male';
    if (type === 'female') return gender === 'female';
    return true;
  }

  function filteredVoices() {
    const type = els.voiceTypeSelect.value;
    const selectedVoice = els.voiceSelect.value || state.settings.voice_id;
    const voices = state.voices.filter(voice => voiceMatchesType(voice, type));
    if (voices.length) return voices;
    if (selectedVoice) {
      const current = state.voices.find(voice => voice.voice_id === selectedVoice);
      if (current) return [current];
    }
    return state.voices;
  }

  function renderVoices() {
    const current = state.settings.voice_id || '';
    const voices = filteredVoices();
    els.voiceSelect.innerHTML = voices.map(voice => {
      const meta = [voice.gender, voice.language].filter(Boolean).join(' · ');
      const label = voice.name + (meta ? ' — ' + meta : '');
      return option(voice.voice_id, label, voice.voice_id === current);
    }).join('');
  }

  function setSlider(input, label, value) {
    input.value = value;
    label.textContent = Number(value).toFixed(2);
  }

  function applySettings(settings) {
    state.settings = settings || {};
    els.voiceTypeSelect.value = 'all';
    renderVoices();
    els.languageSelect.value = state.settings.language || 'ru';
    setSlider(els.speedInput, els.speedValue, state.settings.speed ?? 1);
  }

  function collectSettings() {
    const voice = state.voices.find(item => item.voice_id === els.voiceSelect.value) || {};
    return {
      telegram_id: state.telegramId,
      voice_id: els.voiceSelect.value,
      voice_name: voice.name || 'HeyGen Voice',
      model_id: 'starfish',
      language: els.languageSelect.value,
      speed: Number(els.speedInput.value),
      output_format: 'mp3'
    };
  }

  async function loadBootstrap() {
    const user = getTelegramUser();
    state.telegramId = Number(user.id || new URLSearchParams(location.search).get('telegram_id') || 0);

    const response = await fetch('/api/heygen-voice/bootstrap?telegram_id=' + encodeURIComponent(state.telegramId));
    const data = await response.json();
    if (!data.success) throw new Error(data.error || 'Unable to load settings');

    state.voices = data.voices || [];
    if (!state.voices.length) throw new Error('HeyGen Starfish voices are unavailable');

    applySettings(data.settings || data.defaults || {});

    if (data.warnings && data.warnings.length) {
      console.warn('HEYGEN VOICE BOOTSTRAP WARNINGS', data.warnings);
      toast('HeyGen API требует проверки ключа или доступа.');
    }
  }

  async function save() {
    if (!state.telegramId) {
      toast('Откройте страницу из Telegram Mini App');
      return;
    }

    if (!els.voiceSelect.value) {
      toast('Выберите голос');
      return;
    }

    els.saveButton.disabled = true;
    els.saveButton.textContent = 'Сохраняется...';

    try {
      const settingsPayload = collectSettings();
      console.log('HEYGEN VOICE SETTINGS FRONTEND SAVE', {
        telegram_id: settingsPayload.telegram_id,
        voice_id: settingsPayload.voice_id,
        voice_name: settingsPayload.voice_name,
        model_id: settingsPayload.model_id,
        language: settingsPayload.language,
        speed: settingsPayload.speed
      });

      const response = await fetch('/api/heygen-voice/settings', {
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

  function bind() {
    els.voiceTypeSelect = document.getElementById('voiceTypeSelect');
    els.voiceSelect = document.getElementById('voiceSelect');
    els.languageSelect = document.getElementById('languageSelect');
    els.speedInput = document.getElementById('speedInput');
    els.speedValue = document.getElementById('speedValue');
    els.saveButton = document.getElementById('saveButton');

    els.voiceTypeSelect.addEventListener('change', renderVoices);
    els.speedInput.addEventListener('input', () => {
      els.speedValue.textContent = Number(els.speedInput.value).toFixed(2);
    });
    els.saveButton.addEventListener('click', save);
  }

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
      toast('Не удалось загрузить HeyGen Voice');
      console.error(error);
      applySettings({
        voice_id: '',
        voice_name: 'Auto',
        model_id: 'starfish',
        language: 'ru',
        speed: 1
      });
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
