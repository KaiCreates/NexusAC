/* Shared helpers. Every call goes to /api/control/* with the session cookie. */

async function api(path, body, method) {
  const options = {
    method: method || (body === undefined ? 'GET' : 'POST'),
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
  };
  if (body !== undefined) options.body = JSON.stringify(body);
  let response;
  try {
    response = await fetch('/api/control' + path, options);
  } catch (error) {
    return { ok: false, status: 0, error: 'Cannot reach the website. Is it still running?' };
  }
  const type = response.headers.get('content-type') || '';
  const data = type.includes('application/json') ? await response.json().catch(() => ({})) : {};
  if (!response.ok) {
    const detail = Array.isArray(data.details) && data.details.length
      ? ' (' + data.details[0] + ')' : '';
    return { ok: false, status: response.status, error: (data.error || 'Request failed.') + detail };
  }
  return { ok: true, status: response.status, data };
}

function note(element, text, kind) {
  if (!element) return;
  element.hidden = false;
  element.className = 'form-message' + (kind ? ' ' + kind : '');
  element.textContent = text;
}

function escapeHtml(value) {
  return String(value === undefined || value === null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/* Relative time from a unix seconds value. */
function ago(seconds, reference) {
  if (!seconds) return 'never';
  const delta = Math.max(0, (reference || Math.floor(Date.now() / 1000)) - Number(seconds));
  if (delta < 60) return delta + 's ago';
  if (delta < 3600) return Math.floor(delta / 60) + 'm ago';
  if (delta < 86400) return Math.floor(delta / 3600) + 'h ago';
  return Math.floor(delta / 86400) + 'd ago';
}

function duration(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  const days = Math.floor(value / 86400);
  const hours = Math.floor((value % 86400) / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  if (days) return days + 'd ' + hours + 'h';
  if (hours) return hours + 'h ' + minutes + 'm';
  return minutes + 'm';
}

/* The same lucide glyphs the templates use, for markup built in JavaScript. */
const ICON_PATHS = {
  'shield-check': '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  'sliders': '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M1 14h6"/><path d="M9 8h6"/><path d="M17 16h6"/>',
  'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  'scan-line': '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
  'ban': '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
  'activity': '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  'radar': '<path d="M19.07 4.93A10 10 0 0 0 6.99 3.34"/><path d="M4 6h.01"/><path d="M2.29 9.62A10 10 0 1 0 21.31 8.35"/><path d="M16.24 7.76A6 6 0 1 0 8.23 16.67"/><path d="M12 18h.01"/><path d="M17.99 11.66A6 6 0 0 1 15.77 16.67"/><circle cx="12" cy="12" r="2"/>',
  'camera': '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="3"/>',
  'close': '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
};
const ICONS = new Proxy({}, {
  get: (_, name) =>
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
    'aria-hidden="true">' + (ICON_PATHS[name] || '') + '</svg>',
});

/* A side drawer that owns the page while it is open. The live poll must not
   repaint underneath it: that is what makes a dropdown close before you can pick
   from it. Uses <dialog>, so the backdrop and Escape come from the platform. */
const Modal = {
  open: false,
  node: null,
  show(html, onReady) {
    this.close();
    const dialog = document.createElement('dialog');
    dialog.className = 'drawer';
    dialog.innerHTML =
      '<header><div style="min-width:0"></div>' +
      '<button class="icon-button" data-close aria-label="Close">' + ICONS.close + '</button></header>' +
      '<div class="drawer-body">' + html + '</div>';
    document.body.appendChild(dialog);
    this.node = dialog;
    this.open = true;
    dialog.addEventListener('close', () => Modal.close());
    dialog.addEventListener('click', (event) => {
      if (event.target.closest('[data-close]')) Modal.close();
      // A click on the dialog element itself (not its children) is the backdrop.
      if (event.target === dialog) Modal.close();
    });
    dialog.showModal();
    if (onReady) onReady(dialog);
    const first = dialog.querySelector('.drawer-body input, .drawer-body select, .drawer-body textarea');
    if (first) first.focus();
  },
  close() {
    if (!this.node) return;
    const node = this.node;
    this.node = null;
    this.open = false;
    if (node.open) node.close();
    node.remove();
  },
};

/* True while anything is open that a repaint would destroy. */
function busy() {
  if (Modal.open) return true;
  const active = document.activeElement;
  return !!(active && active.matches && active.matches('input, select, textarea'));
}

document.addEventListener('DOMContentLoaded', () => {
  const signout = document.getElementById('signout');
  if (signout) {
    signout.addEventListener('click', async (event) => {
      event.preventDefault();
      await api('/auth/logout', {});
      location.href = '/';
    });
  }
});
