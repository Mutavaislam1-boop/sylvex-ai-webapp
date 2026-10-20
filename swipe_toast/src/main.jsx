// Browser entry for the React Bits SwipeToast (src/SwipeToast.jsx and .css,
// kept exactly as published). The app's notices are plain JS calls, so this
// only exposes window.SylvexSwipeToast.show(); js/ui.js routes toast() here.
// Notices stack in the bottom right corner above everything, newest last.
import { createElement, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

import SwipeToast from './SwipeToast.jsx';
import './host.css';

// The settings from the task.
const TOAST_PROPS = {
  actionLabel: '',
  background: '#27272a',
  color: '#f5f5f5',
  fuseColor: '#51f524',
  width: 356,
  radius: 12,
  slideMs: 400,
  settleBounce: 0.2,
  swipeDistance: 40,
  duration: 4000,
  fuse: 'bottom',
  pauseOnHover: true,
  closeButton: true
};
const MAX_TOASTS = 3;

let push = null;
const pending = [];
let serial = 0;

function Toaster() {
  const [toasts, setToasts] = useState([]);
  useEffect(() => {
    // The same notice while it is still shown is ignored, so extra taps
    // never repeat it.
    push = toast =>
      setToasts(list =>
        list.some(item => item.title === toast.title && item.description === toast.description)
          ? list
          : [...list, toast].slice(-MAX_TOASTS)
      );
    pending.splice(0).forEach(push);
    return () => {
      push = null;
    };
  }, []);
  return createElement(
    'div',
    { className: 'sylvex-toasts' },
    toasts.map(toast =>
      createElement(SwipeToast, {
        key: toast.id,
        ...TOAST_PROPS,
        ...toast.props,
        title: toast.title,
        description: toast.description,
        inline: true,
        onClose: () => setToasts(list => list.filter(item => item.id !== toast.id))
      })
    )
  );
}

function show(title, options = {}) {
  const { description = '', ...props } = options;
  if (!document.querySelector('.sylvex-toasts-root')) {
    const host = document.createElement('div');
    host.className = 'sylvex-toasts-root';
    document.body.appendChild(host);
    createRoot(host).render(createElement(Toaster));
  }
  const toast = { id: ++serial, title: String(title ?? ''), description: String(description ?? ''), props };
  if (push) push(toast);
  else pending.push(toast);
}

window.SylvexSwipeToast = { show, TOAST_PROPS };
