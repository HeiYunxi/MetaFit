// ===== User center API (profile, measurements, history, orders) =====
import { API_URL } from '/app/shared/config.js';
import { authHeaders, getAccessToken } from '/app/shared/auth.js';

async function get(path) {
  const r = await fetch(API_URL + path, { credentials: 'include', headers: authHeaders() });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Request failed'); }
  return await r.json();
}
async function patch(path, body) {
  const r = await fetch(API_URL + path, {
    method: 'PATCH', credentials: 'include', headers: authHeaders(), body: JSON.stringify(body),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Update failed'); }
  return await r.json();
}

export const getProfile = () => get('/users/me');
export const updateProfile = (body) => patch('/users/me', body);
export const updateMeasurements = (body) => patch('/users/me/measurements', body);
export const getOrders = (page = 1) => get(`/users/me/orders?page=${page}`);
export const getBrowseHistory = (page = 1) => get(`/users/me/history/browse?page=${page}`);
export const getChatHistory = (page = 1) => get(`/users/me/history/recommendations?page=${page}`);
export const getTryonHistory = (page = 1) => get(`/users/me/history/tryons?page=${page}`);
export const get3dHistory = (page = 1) => get(`/users/me/history/3dmodels?page=${page}`);
export const getMyCoupons = () => get('/users/me/coupons');
export const getSessionMessages = (sessionId) => get(`/users/me/history/messages?session_id=${encodeURIComponent(sessionId)}`);

export async function uploadBodyPhoto(file) {
  const fd = new FormData();
  fd.append('file', file);
  const headers = {};
  const token = getAccessToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetch(API_URL + '/users/me/photo', {
    method: 'POST', credentials: 'include', headers, body: fd,
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Upload failed'); }
  return await r.json();
}
