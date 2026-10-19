// Browser entry for the React Bits BorderGlow (src/BorderGlow.jsx and .css,
// kept exactly as published). The Store is plain JS, so this only exposes a
// mount API on window; js/store-glow.js wraps each Store card with it and
// hands the card's existing element in as the content.
import { createElement, useLayoutEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';

import BorderGlow from './BorderGlow.jsx';
import './host.css';

// The settings from the task. Agreed changes: the purple edge colour
// (#c084fc) and the gold edge glow (40 80 80) are SYLVEX green, and there
// is no automatic sweep (on load, re-render or plan change) - the glow
// shows only under the pointer. backgroundColor comes from the host (the
// task's #120F17 on dark themes, the card's own colour on light ones).
const GLOW_PROPS = {
  edgeSensitivity: 0,
  glowColor: '140 80 55',
  backgroundColor: '#120F17',
  borderRadius: 23,
  glowRadius: 80,
  glowIntensity: 3,
  coneSpread: 35,
  animated: false,
  colors: ['#10b945', '#f472b6', '#38bdf8']
};

// Puts an element that already exists (a Store card, with its listeners
// and state) inside the React tree, and gives it back on unmount.
function Adopt({ node }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const host = ref.current;
    host.appendChild(node);
    return () => {
      if (node.parentNode === host) host.removeChild(node);
    };
  }, [node]);
  return createElement('div', { ref, style: { display: 'contents' } });
}

function mount(element, node, props) {
  const root = createRoot(element);
  let current = { ...GLOW_PROPS, ...props };
  const render = () => root.render(createElement(BorderGlow, current, createElement(Adopt, { node })));
  render();
  return {
    update(next) {
      current = { ...current, ...next };
      render();
    },
    unmount() {
      root.unmount();
    }
  };
}

window.SylvexStoreGlow = { mount, GLOW_PROPS };
