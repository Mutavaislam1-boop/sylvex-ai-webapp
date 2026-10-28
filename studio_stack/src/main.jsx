// Browser entry for the React Bits Stack (src/Stack.jsx and src/Stack.css as
// published, with the demo Unsplash images removed). Pro Studio is plain JS,
// so this only exposes a mount API on window; webapp/js/cabinet.js loads the
// bundle when a generation's reference images are on screen.
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

import Stack from './Stack.jsx';

// The settings from the task; `cards` and `visible` come from the
// generation's own reference images. Agreed change: radius 16 (was 33), the
// corner rounding Pro Studio's own cards use.
const STACK_PROPS = {
  layout: 'fan',
  sendToBackOnClick: true,
  spread: 0.8,
  depth: 0.5,
  radius: 16,
  frame: 0,
  frameColor: '#ffffff',
  shadow: true,
  tilt: 30,
  threshold: 90,
  speed: 1,
  autoplay: false,
  autoplayDelay: 3000,
  pauseOnHover: false
};

// A video fills its card like an image does (Stack.css styles images only
// and stays the published file).
const VIDEO_STYLE = { display: 'block', width: '100%', height: '100%', objectFit: 'cover', pointerEvents: 'none' };

// One card per reference, in the order the generation used them. An item
// is an image URL or { src, kind }; a video plays muted in its card.
function card(item, index) {
  const src = typeof item === 'string' ? item : String((item && item.src) || '');
  const key = index + ':' + src;
  if (item && item.kind === 'video') {
    return createElement('video', { key, src, muted: true, loop: true, autoPlay: true, playsInline: true, preload: 'metadata', draggable: false, style: VIDEO_STYLE });
  }
  return createElement('img', { key, src, alt: 'Reference ' + (index + 1), draggable: false });
}

function props(items) {
  const list = Array.isArray(items) ? items : [];
  return {
    ...STACK_PROPS,
    cards: list.map(card),
    visible: list.length
  };
}

function mount(element, urls) {
  const root = createRoot(element);
  root.render(createElement(Stack, props(urls)));
  return {
    unmount() {
      root.unmount();
    }
  };
}

window.SylvexRefStack = { mount, STACK_PROPS };
