(function () {
  const S = (window.SYLVEX = window.SYLVEX || {});

  function telegramPlatform() {
    try {
      return String(window.Telegram?.WebApp?.platform || '').toLowerCase();
    } catch {
      return '';
    }
  }

  function detectType() {
    const platform = telegramPlatform();
    const ua = String(navigator.userAgent || '');
    const uaDataMobile = navigator.userAgentData && typeof navigator.userAgentData.mobile === 'boolean'
      ? navigator.userAgentData.mobile
      : null;
    const touchPoints = Number(navigator.maxTouchPoints || 0);
    const coarsePointer = Boolean(window.matchMedia && window.matchMedia('(pointer: coarse)').matches);
    const touchCapable = touchPoints > 0 && coarsePointer;

    const isIPad = /iPad/i.test(ua) || (/Macintosh/i.test(ua) && touchPoints > 1);
    const isAndroid = /Android/i.test(ua);
    const isAndroidTablet = isAndroid && !/Mobile/i.test(ua);
    const isKnownTablet = isIPad || isAndroidTablet || /Tablet|PlayBook|Silk/i.test(ua);
    const isKnownPhone = /iPhone|iPod|Windows Phone|Opera Mini|IEMobile/i.test(ua)
      || (isAndroid && /Mobile/i.test(ua))
      || uaDataMobile === true;
    const desktopTelegram = new Set(['tdesktop', 'macos', 'unigram', 'windows', 'linux']);

    if (desktopTelegram.has(platform)) return 'desktop';
    if (isKnownTablet) return 'tablet';
    if (isKnownPhone) return 'mobile';
    if ((platform === 'ios' || platform === 'android') && touchCapable) return 'mobile';
    if (touchCapable && uaDataMobile !== false) return 'mobile';
    return 'desktop';
  }

  const type = detectType();
  const api = Object.freeze({
    type,
    platform: telegramPlatform(),
    isDesktop: type === 'desktop',
    isMobile: type === 'mobile',
    isTablet: type === 'tablet',
    usesVirtualKeyboard: type === 'mobile' || type === 'tablet',
  });
  S.device = api;
  document.documentElement.dataset.deviceType = type;
  document.documentElement.classList.add('device-' + type);
  if (document.body) document.body.classList.add('device-' + type);
  document.addEventListener('DOMContentLoaded', function () {
    document.body.classList.add('device-' + type);
  }, { once: true });
  console.log('SYLVEX_DEVICE_DETECTED', { type: api.type, platform: api.platform });
})();
