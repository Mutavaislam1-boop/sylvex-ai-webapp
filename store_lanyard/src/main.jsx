// Browser entry for the React Bits Lanyard (src/Lanyard.jsx, src/Lanyard.css,
// kept exactly as published - `npx shadcn@latest add @react-bits/Lanyard-JS-CSS`).
// The Mini App is plain JS, so this only exposes a tiny mount API on window;
// webapp/js/store-lanyard.js loads the bundle on demand and passes the props.
import { createElement } from 'react';
import { createRoot } from 'react-dom/client';

import Lanyard from './Lanyard.jsx';

function mount(element, props) {
  const root = createRoot(element);
  let current = { ...props };
  root.render(createElement(Lanyard, current));
  return {
    update(next) {
      current = { ...current, ...next };
      root.render(createElement(Lanyard, current));
    },
    unmount() {
      root.unmount();
    }
  };
}

window.SylvexLanyard = { mount };
