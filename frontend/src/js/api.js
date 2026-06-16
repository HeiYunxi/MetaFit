// ===== Backend API calls =====
import { API_URL } from './config.js';

/** POST /recommend — multi-turn fashion recommendation (RAG) */
export async function recommend(question) {
  const url = (API_URL || 'http://localhost:8000').replace(/\/$/, '') + '/recommend';
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question })
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || data.message || 'Recommendation failed');
  return data;  // { answer, products[] }
}

/** POST /try-on — virtual try-on (person photo + garment URL) */
export async function tryOn(personImageFile, productImageUrl, productName, brand) {
  const fd = new FormData();
  fd.append('person_image', personImageFile);
  fd.append('product_image_url', productImageUrl);
  fd.append('product_name', productName || '');
  fd.append('brand', brand || '');
  const r = await fetch(API_URL + '/try-on', { method: 'POST', body: fd });
  const data = await r.json();
  if (!data.success) throw new Error(data.message || 'Try-on failed');
  return data;  // { success, tryon_image_url, tryon_image_base64 }
}

/** POST /img2model — image-to-3D via Tripo3D (synchronous, mesh-only, legacy) */
export async function img2model(imageUrl, imageBase64, filenamePrefix) {
  const body = imageUrl ? { image_url: imageUrl } : { image_base64: imageBase64 };
  const r = await fetch(API_URL + '/img2model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
  poseNormalize = false,
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

  const r = await fetch(API_URL + '/img2model/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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

/** GET /trending?limit=N — trending products */
export async function fetchTrending(limit = 12) {
  const r = await fetch(API_URL + `/trending?limit=${limit}`);
  const data = await r.json();
  if (!r.ok || !data.products) throw new Error('Failed to load trending');
  return data.products;
}
