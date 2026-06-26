// ===== Shared auth module: in-memory token + session management =====
import { API_URL } from '/app/shared/config.js';

let accessToken = null;
let currentUser = null;
const listeners = new Set();

const REFRESH_URL = API_URL + '/auth/refresh';
const LOGIN_URL = API_URL + '/auth/login';
const REGISTER_URL = API_URL + '/auth/register';
const LOGOUT_URL = API_URL + '/auth/logout';
const ME_URL = API_URL + '/auth/me';

// ---- State accessors ----
export function getAccessToken() { return accessToken; }
export function getCurrentUser() { return currentUser; }
export function isLoggedIn() { return !!currentUser; }
export function isMerchant() {
  return currentUser && (currentUser.role === 'merchant' || currentUser.role === 'admin');
}

export function authHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
  const tid = getThreadId();
  if (tid) headers['X-Session-Id'] = tid;
  return headers;
}

// ---- Change notification ----
export function onAuthChange(cb) {
  listeners.add(cb);
  cb(currentUser);                 // fire immediately with current state
  return () => listeners.delete(cb);
}
function notify() { listeners.forEach((cb) => { try { cb(currentUser); } catch {} }); }

export function setSession(token, user) {
  accessToken = token;
  currentUser = user;
  notify();
}
export function clearSession() {
  accessToken = null;
  currentUser = null;
  notify();
}

// ---- Server interactions ----
export async function tryRefresh() {
  try {
    const r = await fetch(REFRESH_URL, { method: 'POST', credentials: 'include' });
    if (r.ok) {
      const data = await r.json();
      setSession(data.access_token, data.user);
      return true;
    }
  } catch {}
  return false;
}

export async function fetchMe() {
  if (!accessToken) return null;
  try {
    const r = await fetch(ME_URL, { headers: authHeaders() });
    if (r.ok) {
      const data = await r.json();
      currentUser = data.user;
      notify();
      return currentUser;
    }
  } catch {}
  return null;
}

export async function register(username, email, password, gender, measurements) {
  const r = await fetch(REGISTER_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ username, email, password, gender, body_measurements: measurements }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Registration failed');
  setSession(data.access_token, data.user);
  return data;
}

export async function login(usernameOrEmail, password) {
  const r = await fetch(LOGIN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-Id': getThreadId() || '' },
    credentials: 'include',
    body: JSON.stringify({ login: usernameOrEmail, password }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Login failed');
  setSession(data.access_token, data.user);
  return data;
}

export async function logout() {
  try { await fetch(LOGOUT_URL, { method: 'POST', credentials: 'include' }); } catch {}
  clearSession();
}

// ---- Helpers ----
export function getThreadId() {
  const match = document.cookie.match(/(?:^|;\s*)thread_id=([^;]*)/);
  return match ? match[1] : null;
}

/**
 * Ensure we know whether the user is logged in (call once on page load).
 * Resolves after attempting a silent refresh via the HttpOnly cookie.
 */
export async function initAuth() {
  if (currentUser) return currentUser;
  await tryRefresh();
  return currentUser;
}
