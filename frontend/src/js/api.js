// ===== Backend API calls =====
import { API_URL } from './config.js';
import { getAccessToken, getThreadId } from './auth.js';

/** Build common headers with optional auth */
function headers() {
  const h = { 'Content-Type': 'application/json' };
  const token = getAccessToken();
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

/** POST /recommend — multi-turn fashion recommendation (RAG) */
export async function recommend(question) {
  const url = (API_URL || 'http://localhost:8000').replace(/\/$/, '') + '/recommend';
  const body = { question };
  const tid = getThreadId();
  // Backend reads thread_id from cookie, but also pass for robustness
  const r = await fetch(url, {
    method: 'POST',
    headers: headers(),
    credentials: 'include',
    body: JSON.stringify(body)
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || data.message || 'Recommendation failed');
  return data;  // { answer, products[], thread_id }
}

/** Auth headers for multipart (no Content-Type so the browser sets the boundary). */
function multipartHeaders() {
  const h = {};
  const token = getAccessToken();
  if (token) h['Authorization'] = `Bearer ${token}`;
  const tid = getThreadId();
  if (tid) h['X-Session-Id'] = tid;
  return h;
}

/** POST /try-on — virtual try-on (person photo + garment URL) */
export async function tryOn(personImageFile, productImageUrl, productName, brand, productId) {
  const fd = new FormData();
  fd.append('person_image', personImageFile);
  fd.append('product_image_url', productImageUrl);
  fd.append('product_name', productName || '');
  fd.append('brand', brand || '');
  if (productId) fd.append('product_id', String(productId));
  const r = await fetch(API_URL + '/try-on', {
    method: 'POST',
    body: fd,
    headers: multipartHeaders(),
    credentials: 'include',
  });
  const data = await r.json();
  if (!data.success) throw new Error(data.message || 'Try-on failed');
  return data;  // { success, tryon_image_url, tryon_image_base64 }
}

/** POST /img2model — image-to-3D via Tripo3D (synchronous, mesh-only, legacy) */
export async function img2model(imageUrl, imageBase64, filenamePrefix) {
  const body = imageUrl ? { image_url: imageUrl } : { image_base64: imageBase64 };
  const r = await fetch(API_URL + '/img2model', {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ ...body, filename_prefix: filenamePrefix || 'tryon_model' })
  });
  const data = await r.json();
  if (!data.success) throw new Error(data.message || '3D generation failed');
  return data;  // { success, model_path }
}

/**
 * POST /img2model/submit — async 3-stage pipeline (mesh → rig → animation).
 * Returns immediately with a task id; poll getImg2ModelStatus() until done.
 */
export async function submitImg2Model({
  imageUrl, imageBase64, filenamePrefix,
  rigEnabled = false, animationEnabled = false, animationPreset = 'idle',
  poseNormalize = false, productId = null,
} = {}) {
  const rig = rigEnabled || animationEnabled;
  const body = {
    filename_prefix: filenamePrefix || 'tryon_model',
    pose_normalization: { enabled: poseNormalize || rig },
    rig: { enabled: rig, spec: animationEnabled ? 'tripo' : 'mixamo' },
    animation: { enabled: animationEnabled, preset: animationPreset || 'idle' },
  };
  if (imageUrl) body.image_url = imageUrl;
  else if (imageBase64) body.image_base64 = imageBase64;
  if (productId) body.product_id = productId;

  const tid = getThreadId();
  const r = await fetch(API_URL + '/img2model/submit', {
    method: 'POST',
    headers: { ...headers(), ...(tid ? { 'X-Session-Id': tid } : {}) },
    credentials: 'include',
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || data.message || 'Submit failed');
  return data;  // { task_id, status_url }
}

/** GET /img2model/status/{id} — poll one async task's status. */
export async function getImg2ModelStatus(taskId) {
  const r = await fetch(API_URL + '/img2model/status/' + taskId);
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Status check failed');
  return data;  // { state, stage, progress, mesh, rig, animation, download_url, error }
}

/** GET /users/me/history/messages?session_id=... — past conversation of a session. */
export async function getSessionMessages(sessionId) {
  const r = await fetch(API_URL + '/users/me/history/messages?session_id=' + encodeURIComponent(sessionId), {
    headers: headers(),
    credentials: 'include',
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Failed to load messages');
  return data;  // { session_id, items: [{role, content, created_at}] }
}

/** GET /trending?limit=N — trending products */
export async function fetchTrending(limit = 12) {
  const r = await fetch(API_URL + `/trending?limit=${limit}`);
  const data = await r.json();
  if (!r.ok || !data.products) throw new Error('Failed to load trending');
  return data.products;
}
