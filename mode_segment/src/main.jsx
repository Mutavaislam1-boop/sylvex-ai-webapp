// Browser entry for the React Bits RubberSegment (src/RubberSegment.jsx and
// .css, kept exactly as published). Pro Studio is plain JS, so this only
// exposes a mount API on window; js/cabinet.js passes the existing mode
// tabs' icons and clicks the matching tab on a change.
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

import RubberSegment from './RubberSegment.jsx';
import './host.css';

// The settings from the task. The size is fitted to each layout's old tab
// box in host.css, so the composer keeps its level.
const SEGMENT_PROPS = {
  trackColor: '#27272a',
  thumbColor: '#ffffff',
  textColor: '#ffffff',
  activeTextColor: '#18181b',
  size: 'lg',
  radius: 18,
  inset: 3,
  equalSlots: true,
  stretch: 100,
  squash: 3,
  speed: 1.4,
  glide: 45,
  draggable: true,
  disabled: false
};

// The tab's own SVG (static markup from cabinet.html), labelled for screen readers.
const icon = tab =>
  createElement('span', {
    className: 'mode-segment-icon',
    role: 'img',
    'aria-label': tab.label,
    dangerouslySetInnerHTML: { __html: tab.html }
  });

function mount(element, tabs, props) {
  const root = createRoot(element);
  const items = tabs.map(tab => ({ value: tab.value, label: '', icon: icon(tab) }));
  let current = { ...SEGMENT_PROPS, className: 'mode-segment', 'aria-label': 'Studio mode', ...props };
  const render = () => root.render(createElement(RubberSegment, { ...current, items }));
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

window.SylvexModeSegment = { mount, SEGMENT_PROPS };
