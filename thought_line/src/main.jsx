// Browser entry for ThoughtLine (src/ThoughtLine.jsx and .css, kept exactly
// as provided). Pro Studio is plain JS, so this only exposes a mount API on
// window. js/cabinet.js passes the confirmed stages of the generation; the
// timer runs from the job's real start (startedAt) to its real end
// (finishedAt) through the component's own `elapsed` prop.
import { createElement, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

import ThoughtLine from './ThoughtLine.jsx';
import './host.css';

// The settings from the task. The colour is a concrete theme colour from the
// host (--sx-thought-color): with the default currentColor, the shimmering
// label would resolve it against its own transparent text and vanish.
const LINE_PROPS = {
  color: 'var(--sx-thought-color, #a1a1aa)',
  glyph: 'sparkle',
  fontSize: 16,
  breathPeriod: 1.6,
  breathDepth: 0.45,
  settleDuration: 350,
  settleBlur: 2,
  collapsible: true,
  collapseOnSettle: true,
  showTimer: true
};

function Live({ startedAt, finishedAt, failed, className, ...props }) {
  const [now, setNow] = useState(Date.now);
  const working = props.working !== false;
  useEffect(() => {
    if (!working || !startedAt) return undefined;
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, [working, startedAt]);
  const end = working ? now : finishedAt || now;
  const elapsed = startedAt ? Math.max(0, (end - startedAt) / 1000) : undefined;
  const classes = ['sx-thought', failed ? 'sx-thought--failed' : '', className || ''].filter(Boolean).join(' ');
  return createElement(ThoughtLine, { ...LINE_PROPS, ...props, working, elapsed, className: classes });
}

function mount(element, props) {
  const root = createRoot(element);
  let current = { ...props };
  const render = () => root.render(createElement(Live, current));
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

window.SylvexThoughtLine = { mount, LINE_PROPS };
