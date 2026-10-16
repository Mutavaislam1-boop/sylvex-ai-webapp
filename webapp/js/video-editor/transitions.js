// SYLVEX transition library. A transition in the project is one of these
// ids; each describes an effect in engine-neutral terms (kind + direction /
// colour). An engine adapter lists the kinds it can draw and maps them to
// its own effects, so the library and its previews belong to SYLVEX, not to
// the engine. Ids equal to a bare kind ('cross-fade', 'push', ...) are kept
// for projects saved before the library existed.

const DIRS = { left: 'влево', right: 'вправо', up: 'вверх', down: 'вниз' };

function directional(kind, label, group, dirs = ['left', 'right', 'up', 'down']) {
  return dirs.map((dir) => ({ id: kind + '-' + dir, kind, dir, group, label: label + ' ' + DIRS[dir] }));
}

export const TRANSITIONS = [
  { id: 'cross-fade', kind: 'cross-fade', group: 'Плавные', label: 'Наплыв' },
  { id: 'fade-to-black', kind: 'fade-to-black', group: 'Плавные', label: 'Через чёрный' },
  { id: 'fade-to-white', kind: 'fade-to-white', group: 'Плавные', label: 'Через белый' },
  { id: 'fade', kind: 'fade', group: 'Плавные', label: 'Через цвет', color: '#5572f5', colorable: true },
  { id: 'cross-blur', kind: 'cross-blur', group: 'Плавные', label: 'Размытие' },
  { id: 'gradient-fade', kind: 'gradient-fade', dir: 'right', group: 'Плавные', label: 'Градиент' },
  { id: 'cross-zoom', kind: 'cross-zoom', group: 'Движение', label: 'Зум' },
  { id: 'cross-warp', kind: 'cross-warp', group: 'Движение', label: 'Деформация' },
  { id: 'cross-spin', kind: 'cross-spin', dir: 'clockwise', group: 'Движение', label: 'Вращение' },
  { id: 'cross-spin-ccw', kind: 'cross-spin', dir: 'counterclockwise', group: 'Движение', label: 'Вращение назад' },
  ...directional('push', 'Сдвиг', 'Движение'),
  ...directional('slide', 'Наезд', 'Движение'),
  ...directional('stack', 'Стопка', 'Движение', ['left', 'right']),
  ...directional('wipe', 'Шторка', 'Шторки'),
  ...directional('color-wipe', 'Цветная шторка', 'Шторки', ['left', 'right']).map((item) => Object.assign(item, { color: '#ffffff', colorable: true })),
  { id: 'line-wipe', kind: 'line-wipe', group: 'Шторки', label: 'Линия' },
  { id: 'clock-wipe', kind: 'clock-wipe', group: 'Шторки', label: 'Часы' },
  { id: 'two-stripes', kind: 'two-stripes', dir: 'horizontal', group: 'Шторки', label: 'Две полосы' },
  { id: 'two-stripes-vertical', kind: 'two-stripes', dir: 'vertical', group: 'Шторки', label: 'Две полосы вертикально' },
  { id: 'splice', kind: 'splice', dir: 'left', group: 'Графика', label: 'Разрез' },
  { id: 'diagonal-splice', kind: 'diagonal-splice', group: 'Графика', label: 'Диагональ' },
  { id: 'chop', kind: 'chop', group: 'Графика', label: 'Нарезка' },
];

const LEGACY = { push: 'push-left', slide: 'slide-left', stack: 'stack-right', wipe: 'wipe-left', 'color-wipe': 'color-wipe-left' };

export function transitionById(id) {
  const key = LEGACY[id] || id;
  return TRANSITIONS.find((item) => item.id === key) || null;
}

// Library entries the current engine can draw, in library order.
export function availableTransitions(kinds) {
  const supported = new Set(kinds || []);
  return TRANSITIONS.filter((item) => supported.has(item.kind));
}

// Small looping preview: clip A gives way to clip B with the effect's own
// motion. `a`/`b` are { url, key } of frames of the real neighbouring clips
// (`key` lets a frame that is still being made appear later) or empty for
// the neutral preview colours.
export function transitionPreview(item, a = {}, b = {}) {
  const layer = (frame, cls) => {
    const url = frame && frame.url ? String(frame.url).replace(/"/g, '') : '';
    return '<i class="' + cls + '"' + (frame && frame.key ? ' data-frame="' + String(frame.key).replace(/"/g, '') + '"' : '') + (url ? ' style="background-image:url(&quot;' + url + '&quot;)"' : '') + '></i>';
  };
  const color = item.color ? ' style="--tp-color:' + item.color + '"' : '';
  return '<span class="ve-tp ve-tp-' + item.kind + (item.dir ? ' ve-tp-' + item.dir : '') + '"' + color + '>' + layer(a, 've-tp-a') + layer(b, 've-tp-b') + '<i class="ve-tp-fx"></i></span>';
}
