// Static data used to render dynamic UI parts.
(function () {
  const toolsData = [
    { icon: '🎨', k: 'image' }, { icon: '✍️', k: 'text' },
    { icon: '🎙️', k: 'voice' }, { icon: '🎬', k: 'video' },
    { icon: '🧠', k: 'chat' },  { icon: '🔍', k: 'up' },
    { icon: '🎵', k: 'music' }, { icon: '📝', k: 'tr' }
  ];

  const pillsData = [
    { icon: '📷', k: 'photo' }, { icon: '🎬', k: 'video' },
    { icon: '🎙️', k: 'voice' }, { icon: '🎵', k: 'music' },
    { icon: '📝', k: 'text' }
  ];

  const histData = [
    { icon: '🎨', tk: 'hist1', sk: 'hist1s', status: 'done',    label: 'done' },
    { icon: '✍️', tk: 'hist2', sk: 'hist2s', status: 'done',    label: 'done' },
    { icon: '🎙️', tk: 'hist3', sk: 'hist3s', status: '',        label: 'ready' },
    { icon: '🎬', tk: 'hist4', sk: 'hist4s', status: 'pending', label: 'rendering' },
    { icon: '🔍', tk: 'hist5', sk: 'hist5s', status: 'done',    label: 'done' },
    { icon: '🎵', tk: 'hist6', sk: 'hist6s', status: 'done',    label: 'done' }
  ];

  const shopData = [
    { icon: '⚡️',  tokens: 500,  price: '$4.99' },
    { icon: '💎', tokens: 1200, price: '$9.99', pop: true },
    { icon: '🚀', tokens: 3000, price: '$19.99' },
    { icon: '👑', tokens: 8000, price: '$49.99' }
  ];

  const catsData = [
    { k: 'video', icon: '🎬' }, { k: 'image', icon: '🖼️' },
    { k: 'music', icon: '🎵' }, { k: 'text',  icon: '📝' },
    { k: 'voice', icon: '🎙️' }
  ];

  // Studio mode strip used inside Pro Studio.
  const STUDIO_MODES = [
    { k: 'video', icon: '🎬' }, { k: 'image', icon: '🖼️' },
    { k: 'voice', icon: '🎙️' }, { k: 'music', icon: '🎵' },
    { k: 'text',  icon: '📝' }
  ];

  // Generation control options.
  const CTRL = {
    model:  ["SYLVEX v3", "SYLVEX Turbo", "GPT-Vision 4", "Claude Opus", "Gemini Pro"],
    format: ["PNG", "JPEG", "WEBP", "SVG"],
    video:  ["MP4 · 16:9", "MP4 · 9:16", "MOV · 1:1", "WEBM · 4:3"],
    res:    ["1024 × 1024", "1920 × 1080", "2048 × 2048", "4K UHD", "HD 720p"],
    time:   ["~ 4s · Ultra", "~ 8s · Fast", "~ 20s · Quality", "~ 45s · Max"]
  };
  const CTRL_IDX = { model: 0, format: 0, video: 0, res: 0, time: 1 };

  // Pricing model in ⚡️ tokens.
  const CAT_PRICE = { video: 50, image: 10, music: 30, text: 5, voice: 20 };
  const CTRL_PRICE = {
    model:  [0, 5, 10, 15, 20],
    format: [0, 0, 2, 4],
    video:  [0, 0, 3, 5],
    res:    [0, 5, 10, 25, 3],
    time:   [20, 8, 15, 30]
  };

  window.SYLVEX = window.SYLVEX || {};
  Object.assign(window.SYLVEX, {
    toolsData, pillsData, histData, shopData, catsData,
    STUDIO_MODES, CTRL, CTRL_IDX, CAT_PRICE, CTRL_PRICE
  });
})();