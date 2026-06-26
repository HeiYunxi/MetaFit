// ===== Merchant API calls =====
const API = window.location.origin;

function getToken() {
  // Try to read from cookie or sessionStorage (set by auth.js in main app)
  return sessionStorage.getItem('merchant_token') || '';
}

function authHeaders() {
  const h = { 'Content-Type': 'application/json' };
  const t = getToken();
  if (t) h['Authorization'] = `Bearer ${t}`;
  return h;
}

async function request(method, path, body) {
  const opts = { method, headers: authHeaders(), credentials: 'include' };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  if (r.status === 401) { window.location.href = '/merchant#login'; throw new Error('Unauthorized'); }
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

// ---- Profile ----
export async function fetchProfile() {
  return request('GET', '/merchant/profile');
}

// ---- Products ----
export async function fetchProducts(page = 1, search = '', label = '', active = null) {
  const params = new URLSearchParams({ page, page_size: 20 });
  if (search) params.set('search', search);
  if (label) params.set('label', label);
  if (active !== null) params.set('is_active', active);
  return request('GET', `/merchant/products?${params}`);
}

export async function fetchProduct(id) {
  return request('GET', `/merchant/products/${id}`);
}

export async function createProduct(data) {
  return request('POST', '/merchant/products', data);
}

export async function updateProduct(id, data) {
  return request('PUT', `/merchant/products/${id}`, data);
}

export async function deleteProduct(id) {
  return request('DELETE', `/merchant/products/${id}`);
}

export async function updateSizes(productId, sizes) {
  return request('POST', `/merchant/products/${productId}/sizes`, sizes);
}

// ---- Index Rebuild ----
export async function rebuildIndex() {
  return request('POST', '/merchant/products/reindex');
}

export async function getRebuildStatus() {
  return request('GET', '/merchant/products/reindex/status');
}

// ---- Image Upload ----
export async function uploadImage(file) {
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(API + '/merchant/upload/image', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${getToken()}` },
    credentials: 'include',
    body: fd,
  });
  if (!r.ok) throw new Error('Upload failed');
  return await r.json();
}

// ---- Orders ----
export async function fetchMerchantOrders(page = 1) {
  return request('GET', `/merchant/orders?page=${page}&page_size=20`);
}

// ---- Auth ----
export async function merchantLogin(username, password) {
  const r = await fetch(API + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ login: username, password }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Login failed');
  if (data.user && (data.user.role === 'merchant' || data.user.role === 'admin')) {
    sessionStorage.setItem('merchant_token', data.access_token);
    sessionStorage.setItem('merchant_user', JSON.stringify(data.user));
    return data;
  }
  throw new Error('Account is not a merchant. Apply for merchant access first.');
}

export async function merchantRegister(username, email, password) {
  const r = await fetch(API + '/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ username, email, password, role: 'merchant' }),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Register failed');
  if (data.user && (data.user.role === 'merchant' || data.user.role === 'admin')) {
    sessionStorage.setItem('merchant_token', data.access_token);
    sessionStorage.setItem('merchant_user', JSON.stringify(data.user));
    return data;
  }
  throw new Error('Merchant registration failed');
}

export function getMerchantUser() {
  try { return JSON.parse(sessionStorage.getItem('merchant_user') || 'null'); } catch { return null; }
}

export function logout() {
  sessionStorage.removeItem('merchant_token');
  sessionStorage.removeItem('merchant_user');
  window.location.href = '/merchant';
}
