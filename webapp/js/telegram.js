// Telegram WebApp SDK bootstrap and haptics helpers.
(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
   
    } catch (e) {}
  }

if (tg.setHeaderColor && parseFloat(tg.version) >= 6.9) {
  tg.setHeaderColor('#030308');
}


  window.SYLVEX = window.SYLVEX || {};
  window.SYLVEX.tg = tg;

  // Haptic helpers used across the app.
  window.SYLVEX.haptic = {
    select() { try { tg && tg.HapticFeedback && tg.HapticFeedback.selectionChanged(); } catch (e) {} },
    impact(kind) { try { tg && tg.HapticFeedback && tg.HapticFeedback.impactOccurred(kind || 'light'); } catch (e) {} },
    notify(kind) { try { tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred && tg.HapticFeedback.notificationOccurred(kind || 'success'); } catch (e) {} },
  };

  // Send arbitrary data back to the bot.
  window.SYLVEX.sendToBot = function (payload) {
    if (!tg || !tg.sendData) return false;
    try { tg.sendData(typeof payload === 'string' ? payload : JSON.stringify(payload)); return true; }
    catch (e) { return false; }
  };
})();
