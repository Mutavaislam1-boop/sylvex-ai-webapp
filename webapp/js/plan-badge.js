/*
 * Plan badge: the active subscription's name as a small coloured badge -
 * Starter, Pro, Max, Ultra and Creator each have their own colour - and its
 * period in words, instead of the raw key ("starter_month"). The same file
 * runs in the Mini App (Russian) and on the website (English).
 *
 *   SylvexPlanBadge.parse('pro_year')            -> { id: 'pro', name: 'Pro', period: 'year' }
 *   SylvexPlanBadge.html('pro_year')             -> '<span class="sx-plan sx-plan--pro">…Pro</span>'
 *   SylvexPlanBadge.periodLabel('pro_year', 'ru') -> 'год'
 */
(function (global) {
  'use strict';
  if (global.SylvexPlanBadge) return;
  var PLANS = { starter: 'Starter', pro: 'Pro', max: 'Max', ultra: 'Ultra', creator: 'Creator' };
  var PERIOD = { en: { month: 'Monthly', year: 'Yearly' }, ru: { month: 'месяц', year: 'год' } };
  var STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.1 6.4 6.4 2.1-6.4 2.1L12 19.5l-2.1-6.4L3.5 11l6.4-2.1z"/></svg>';

  // "starter_month" / "pro_year"; the legacy "month" / "year" keys are Pro.
  function parse(planKey) {
    var key = String(planKey || '').trim().toLowerCase();
    if (!key) return null;
    var cut = key.lastIndexOf('_');
    var id = cut > 0 ? key.slice(0, cut) : 'pro';
    var period = cut > 0 ? key.slice(cut + 1) : key;
    if (!PLANS[id]) return null;
    return { id: id, name: PLANS[id], period: period === 'year' ? 'year' : 'month' };
  }

  function html(planKey) {
    var plan = parse(planKey);
    if (!plan) return '';
    return '<span class="sx-plan sx-plan--' + plan.id + '">' + STAR + plan.name + '</span>';
  }

  function periodLabel(planKey, lang) {
    var plan = parse(planKey);
    return plan ? (PERIOD[lang] || PERIOD.en)[plan.period] : '';
  }

  global.SylvexPlanBadge = { parse: parse, html: html, periodLabel: periodLabel };
})(window);
