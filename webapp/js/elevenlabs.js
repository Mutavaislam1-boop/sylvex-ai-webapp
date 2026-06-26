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

  function option(value, label, selected) {
    return '<option value="' + String(value || '').replace(/"/g, '&quot;') + '"' + (selected ? ' selected' : '') + '>' + label + '</option>';
  }

  function voiceMatchesType(voice, type) {
    if (!type || type === 'all') return true;
    const text = [
      voice.name || '',
      voice.category || '',
      voice.gender || '',
      voice.language || ''
    ].join(' ').toLowerCase();

    if (type === 'male') return text.includes('male') || text.includes('man');
    if (type === 'female') return text.includes('female') || text.includes('woman');
    if (type === 'narration') return text.includes('narrat') || text.includes('news') || text.includes('professional');
    if (type === 'character') return text.includes('character') || text.includes('cartoon') || text.includes('animated');
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

  function renderModels() {
    const current = state.settings.model_id || 'eleven_multilingual_v2';
    els.modelSelect.innerHTML = state.models.map(model => {
      return option(model.model_id, model.name || model.model_id, model.model_id === current);
    }).join('');
  }

  function renderVoices() {
    const current = state.settings.voice_id || '21m00Tcm4TlvDq8ikWAM';
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

  function collectSettings() {
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

  async function loadBootstrap() {
    const user = getTelegramUser();
    state.telegramId = Number(user.id || new URLSearchParams(location.search).get('telegram_id') || 0);

    const response = await fetch('/api/elevenlabs/bootstrap?telegram_id=' + encodeURIComponent(state.telegramId));
    const data = await response.json();
    if (!data.success) throw new Error(data.error || 'Unable to load settings');

    state.voices = data.voices || [];
    state.models = data.models || [];
    applySettings(data.settings || data.defaults || {});
  }

  async function preview() {
    const payload = collectSettings();
    payload.text = 'SYLVEX AI. Проверка выбранного голоса.';
    els.previewButton.disabled = true;
    els.previewButton.textContent = 'Готовится...';

    try {
      const response = await fetch('/api/elevenlabs/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }

      const blob = await response.blob();
      const audioUrl = URL.createObjectURL(blob);
      els.previewAudio.src = audioUrl;
      els.previewAudio.hidden = false;
      await els.previewAudio.play();
    } catch (error) {
      toast('Не удалось воспроизвести пример');
      console.error(error);
    } finally {
      els.previewButton.disabled = false;
      els.previewButton.textContent = 'Прослушать пример';
    }
  }

  async function save() {
    if (!state.telegramId) {
      toast('Откройте страницу из Telegram Mini App');
      return;
    }

    els.saveButton.disabled = true;
    els.saveButton.textContent = 'Сохраняется...';

    try {
      const response = await fetch('/api/elevenlabs/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectSettings())
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Save failed');
      toast('Настройки сохранены');
      if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    } catch (error) {
      toast('Не удалось сохранить настройки');
      console.error(error);
    } finally {
      els.saveButton.disabled = false;
      els.saveButton.textContent = 'Сохранить';
    }
  }

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
    els.previewButton = document.getElementById('previewButton');
    els.saveButton = document.getElementById('saveButton');
    els.previewAudio = document.getElementById('previewAudio');

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
    els.previewButton.addEventListener('click', preview);
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

  document.addEventListener('DOMContentLoaded', init);
})();
