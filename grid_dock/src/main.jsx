// Browser entry for the React Bits Dock (src/Dock.jsx and .css, kept
// exactly as published). Grid Mode is plain JS, so this only exposes a
// mount API on window; js/cabinet.js builds the items from the side panel's
// existing buttons and each item clicks its original button.
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

import Dock from './Dock.jsx';
import './host.css';

// The settings from the task, with the sizes scaled to the side panel's
// existing block (42px buttons, 54px wide panel, 4px gap); magnification
// and distance keep the task's ratios (102 / 60, 200 / 60). theme comes
// from the host: "light" on light Pro Studio themes, "dark" on dark ones.
const DOCK_PROPS = {
  baseItemSize: 42,
  magnification: 71,
  panelHeight: 54,
  distance: 140,
  gap: 4,
  roundness: 0.7,
  accentColor: '#0a84ff',
  badgeColor: '#ff453a',
  position: 'left',
  bounce: true,
  autoHide: false,
  tiles: false,
  showLabels: true,
  showIndicators: false,
  showBadges: true,
  theme: 'dark'
};

function mount(element, items, props) {
  const root = createRoot(element);
  let current = { ...DOCK_PROPS, className: 'studio-grid-dock', ...props };
  let rows = items;
  const render = () => root.render(createElement(Dock, { ...current, items: rows }));
  render();
  return {
    update(nextItems, nextProps) {
      if (nextItems) rows = nextItems;
      if (nextProps) current = { ...current, ...nextProps };
      render();
    },
    unmount() {
      root.unmount();
    }
  };
}

window.SylvexGridDock = { mount, DOCK_PROPS };
