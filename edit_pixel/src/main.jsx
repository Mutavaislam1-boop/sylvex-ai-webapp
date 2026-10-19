// Browser entry for the React Bits PixelCard (src/PixelCard.jsx and .css,
// kept exactly as published). The Edit workspace is plain JS, so this only
// exposes a mount API on window; js/cabinet.js puts its existing photo
// upload button inside the card as the content.
import { createElement, useLayoutEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';

import PixelCard from './PixelCard.jsx';
import './host.css';

// The settings from the task. theme comes from the host: the task's
// "light" on light Pro Studio themes, "dark" on dark ones.
const PIXEL_PROPS = {
  colors: ['#00fd50', '#00fd50', '#00fd50'],
  glowColor: '#10b945',
  shape: 'circle',
  origin: 'center',
  gap: 5,
  pixelSize: 2,
  speed: 35,
  revealDuration: 600,
  spotlight: 0.5,
  glow: 0.5,
  opacity: 0.7,
  fade: 0.7,
  trigger: 'hover',
  radius: 24,
  clickPulse: true,
  intro: true,
  theme: 'light'
};

// Puts an element that already exists (the upload button, with its click
// handler) inside the React tree, and gives it back on unmount.
function Adopt({ node }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const host = ref.current;
    host.appendChild(node);
    return () => {
      if (node.parentNode === host) host.removeChild(node);
    };
  }, [node]);
  return createElement('div', { ref, className: 'edit-pixel-content' });
}

function mount(element, node, props) {
  const root = createRoot(element);
  let current = { ...PIXEL_PROPS, className: 'edit-pixel-card', ...props };
  const render = () => root.render(createElement(PixelCard, current, createElement(Adopt, { node })));
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

window.SylvexEditPixel = { mount, PIXEL_PROPS };
