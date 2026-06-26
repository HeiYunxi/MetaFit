// ===== UI: Chat, Cart, Coins, Ad, Trending, Panels =====
import {
  API_URL, COINS_KEY, COUPONS_KEY, AD_REWARD, AD_VIDEO_URL, COUPON_TIERS,
} from './config.js';
import { loadModel } from './scene.js';
import { recommend, tryOn, submitImg2Model, getImg2ModelStatus, fetchTrending } from './api.js';
import { getCurrentUser, fetchMe } from './auth.js';
import { fetchCart, addToCartAPI, removeFromCartAPI, clearCartAPI } from './cart-api.js';
import { fetchBalance, earnCoinsAPI, dailyCheckin, fetchAvailableCoupons, redeemCouponAPI, fetchMyCoupons } from './coins-api.js';
import { getCoins, addCoins, renderCoinPanelFallback, addToCartFallback } from './fallback-storage.js';

// ---- Shared product state ----
export let selectedProduct = null;
export let tryonResult = null;
export function setSelectedProduct(p) { selectedProduct = p; }
export function hasSelectedProduct() { return !!selectedProduct; }

// ---- Chat UI ----
const chatMessages = document.getElementById('chat-messages');

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

export function addUserMessage(text) {
  const welcome = chatMessages.querySelector('.welcome-msg');
  if (welcome) welcome.remove();
  const div = document.createElement('div');
  div.className = 'msg msg-user';
  div.textContent = text;
  chatMessages.appendChild(div);
  scrollToBottom();
}

/** Replay a past conversation (from generation-history deep link) into the chat panel. */
export function replayMessages(items) {
  if (!items || !items.length) return;
  const welcome = chatMessages.querySelector('.welcome-msg');
  if (welcome) welcome.remove();
  items.forEach((msg) => {
    if (msg.role === 'user') addUserMessage(msg.content || '');
    else addAIMessage(msg.content || '', []);
  });
}

export function addTypingIndicator() {
  const div = document.createElement('div');
  div.className = 'typing-indicator';
  div.id = 'typing';
  div.innerHTML = '<span></span><span></span><span></span>';
  chatMessages.appendChild(div);
  scrollToBottom();
  return div;
}

export function removeTypingIndicator() {
  const el = document.getElementById('typing');
  if (el) el.remove();
}

function formatRecommendation(text) {
  if (!text) return '';
  // Some backend/JSON pipelines double-encode line breaks as the literal two
  // characters "\n" (and "\t"). Without decoding them the whole answer collapses
  // onto one line and headings/lists/links never get parsed. Normalize first.
  const normalized = String(text)
    .replace(/\r\n/g, '\n')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '  ');

  const escaped = normalized
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const inline = (value) => {
    let html = value;
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    html = html.replace(/\((https?:\/\/[^)\s]+)\)/g, '(<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>)');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    return html;
  };

  const lines = escaped.split('\n');
  const blocks = [];
  let listItems = [];

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(`<ul>${listItems.map((item) => `<li>${inline(item)}</li>`).join('')}</ul>`);
    listItems = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      flushList();
      blocks.push('<br>');
      continue;
    }

    const listMatch = line.match(/^[-*]\s+(.+)$/);
    if (listMatch) {
      listItems.push(listMatch[1]);
      continue;
    }

    flushList();

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      blocks.push(`<h${level}>${inline(headingMatch[2])}</h${level}>`);
      continue;
    }

    if (line === '---') {
      blocks.push('<hr>');
      continue;
    }

    blocks.push(`<p>${inline(line)}</p>`);
  }

  flushList();
  return blocks.join('');
}

export function addAIMessage(answer, products) {
  removeTypingIndicator();
  const div = document.createElement('div');
  div.className = 'msg msg-ai';
  let html = '';
  if (answer) {
    html += `<div class="reason">${formatRecommendation(answer)}</div>`;
  }
  if (products && products.length > 0) {
    html += `<div class="products-label">Recommended Items (${products.length})</div>`;
    html += '<div class="chat-products">';
    products.forEach((p, i) => {
      const priceStr = p.price ? `${p.currency || '$'}${p.price}` : '';
      const origPrice = (p.original_price && p.original_price > p.price)
        ? `<span style="text-decoration:line-through;color:#666;font-size:11px;margin-left:6px">${p.currency || '$'}${p.original_price}</span>` : '';
      const discount = p.discount_percentage
        ? `<span style="color:#34d399;font-size:11px;margin-left:4px">-${p.discount_percentage}%</span>` : '';
      html += `
        <div class="chat-product-card" data-index="${i}">
          ${p.image_url ? `<img src="${p.image_url}" alt="" loading="lazy">` : '<div style="width:72px;height:90px;background:#2a2a4a;border-radius:8px"></div>'}
          <div class="chat-product-info">
            <div class="name">${p.product_name || 'Product'}</div>
            <div class="brand">${p.brand || ''} ${p.label ? '· ' + p.label : ''}</div>
            <div class="price">${priceStr}${origPrice}${discount}</div>
            ${p.description ? `<div class="desc">${p.description}</div>` : ''}
            <button class="add-cart-btn" data-add="${i}">🛒 Add to cart</button>
          </div>
        </div>`;
    });
    html += '</div>';
  }
  div.innerHTML = html;
  chatMessages.appendChild(div);

  div.querySelectorAll('.chat-product-card').forEach(card => {
    card.addEventListener('click', () => {
      const idx = parseInt(card.dataset.index);
      document.querySelectorAll('.chat-product-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      selectProduct(products[idx]);
    });
  });
  div.querySelectorAll('.add-cart-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      addToCart(products[parseInt(btn.dataset.add)]);
    });
  });

  scrollToBottom();
}

// Try-on API may return an absolute URL or base64; normalize to a usable <img src>.
function resolveTryOnImageSrc(data) {
  if (!data) return null;
  if (data.tryon_image_base64) {
    return `data:image/png;base64,${data.tryon_image_base64}`;
  }
  if (data.tryon_image_url) {
    const url = data.tryon_image_url;
    if (/^(https?:)?\/\//i.test(url) || url.startsWith('data:')) return url;
    const base = (API_URL || '').replace(/\/$/, '');
    return base + (url.startsWith('/') ? url : '/' + url);
  }
  return null;
}

export function addAITryOnResultMessage({ src, productName, brand }) {
  removeTypingIndicator();
  const div = document.createElement('div');
  div.className = 'msg msg-ai';
  const title = productName || 'selected item';
  const subtitle = brand ? `**${title}** · ${brand}` : `**${title}**`;
  let html = '<div class="tryon-label">Virtual Try-On Result</div>';
  html += `<div class="reason">${formatRecommendation(subtitle)}</div>`;
  html += src
    ? `<img class="tryon-result-image" src="${src}" alt="Virtual try-on result" loading="lazy">`
    : '<div class="reason">Image preview unavailable.</div>';
  html += '<div class="reason" style="margin-top:8px;color:#9ca3af">You can now generate a 3D model from this result.</div>';
  div.innerHTML = html;
  chatMessages.appendChild(div);
  scrollToBottom();
}

export function addErrorMessage(errorText) {
  removeTypingIndicator();
  const div = document.createElement('div');
  div.className = 'msg msg-ai';
  div.innerHTML = `<div class="reason" style="color:#f87171">${errorText}</div>`;
  chatMessages.appendChild(div);
  scrollToBottom();
}

// ---- Product selection ----
export function selectProduct(product) {
  selectedProduct = product;
  document.getElementById('tryon-panel').classList.remove('hidden');
  document.getElementById('model-panel').classList.add('hidden');
  tryonResult = null;
}

// ---- Trending strip ----
export async function loadTrending() {
  const row = document.getElementById('trending-row');
  try {
    const products = await fetchTrending(12);
    if (!products.length) {
      row.innerHTML = '<span style="font-size:12px;color:#666">No trending items.</span>';
      return;
    }
    row.innerHTML = '';
    products.forEach((p) => {
      const priceStr = p.price ? `${p.currency || '$'}${p.price}` : '';
      const card = document.createElement('div');
      card.className = 'trending-card';
      card.innerHTML = `
        ${p.image_url ? `<img src="${p.image_url}" alt="" loading="lazy">` : '<div style="width:100%;height:96px;background:#2a2a4a;border-radius:6px"></div>'}
        <div class="name">${p.product_name || 'Product'}</div>
        <div class="price">${priceStr}</div>
        <button class="add-cart-btn">🛒 Add</button>`;
      card.addEventListener('click', () => {
        document.querySelectorAll('.trending-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        selectProduct(p);
      });
      card.querySelector('.add-cart-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        addToCart(p);
      });
      row.appendChild(card);
    });
  } catch (e) {
    row.innerHTML = '<span style="font-size:12px;color:#f87171">Failed to load trending.</span>';
  }
}

// ---- Cart (API-driven) ----
export async function addToCart(product) {
  try {
    await addToCartAPI(product.id || 0, null, 1);
    await refreshCart();
  } catch (e) {
    console.warn('Cart API failed, using fallback:', e);
    // Fallback to localStorage for backward compatibility
    addToCartFallback(product);
  }
}

async function removeFromCart(itemId) {
  try {
    await removeFromCartAPI(itemId);
    await refreshCart();
  } catch (e) {
    console.warn('Cart remove API failed');
  }
}

async function clearCart() {
  try {
    await clearCartAPI();
    await refreshCart();
  } catch (e) {
    console.warn('Cart clear API failed');
  }
}

export async function renderCart() {
  const container = document.getElementById('cart-items');
  try {
    const data = await fetchCart();
    const items = data.items || [];
    if (items.length === 0) {
      container.innerHTML = '<div class="cart-empty">Your cart is empty.<br>Add items from Trending or recommendations.</div>';
      document.getElementById('cart-badge').textContent = '0';
      return;
    }
    document.getElementById('cart-badge').textContent = items.length;
    container.innerHTML = '';
    items.forEach((item) => {
      const priceStr = item.price ? `${item.currency || '$'}${item.price}` : '';
      const div = document.createElement('div');
      div.className = 'cart-item';
      div.innerHTML = `
        ${item.image_url ? `<img src="${item.image_url}" alt="">` : '<div style="width:48px;height:60px;background:#2a2a4a;border-radius:6px"></div>'}
        <div class="info">
          <div class="name">${item.product_name || 'Product'}</div>
          <div class="price">${priceStr}</div>
        </div>
        <div class="actions">
          <button class="rm-btn">Remove</button>
        </div>`;
      div.querySelector('.rm-btn').addEventListener('click', () => removeFromCart(item.id));
      container.appendChild(div);
    });
    const clear = document.createElement('button');
    clear.className = 'cart-clear-btn';
    clear.textContent = '\u{1F5D1}️ Clear cart';
    clear.addEventListener('click', () => clearCart());
    container.appendChild(clear);
  } catch (e) {
    console.warn('Cart render failed:', e);
    container.innerHTML = '<div class="cart-empty">Cart unavailable.</div>';
  }
}

async function refreshCart() {
  await renderCart();
}

// ---- Coins & coupons UI (API-driven) ----
export async function renderCoinPanel() {
  try {
    // Fetch from API
    const [balanceData, templates, myCoupons] = await Promise.all([
      fetchBalance(),
      fetchAvailableCoupons(),
      fetchMyCoupons(),
    ]);

    document.getElementById('coin-panel-balance').textContent = balanceData.balance;
    const tiersEl = document.getElementById('coupon-tiers');
    tiersEl.innerHTML = '';

    const myC = myCoupons.coupons || [];
    const tpC = templates.coupons || [];

    tpC.forEach((tier, i) => {
      const row = document.createElement('div');
      row.className = 'coupon-tier';
      const afford = balanceData.balance >= tier.min_order_amount / 10;  // Simplified cost estimation
      row.innerHTML = `
        <div>
          <div class="info">${tier.name}</div>
          <div class="cost">${tier.discount_type === 'fixed' ? `￥${tier.discount_value}` : `${tier.discount_value*100}% off`}</div>
        </div>
        <button data-tier="${i}" data-id="${tier.id}" ${afford ? '' : 'disabled'}>Redeem</button>`;
      row.querySelector('button').addEventListener('click', () => redeemCouponAPI(tier.id).then(() => renderCoinPanel()).catch(e => alert(e.message)));
      tiersEl.appendChild(row);
    });

    const myEl = document.getElementById('my-coupons');
    if (myC.length) {
      myEl.innerHTML = '<div style="margin-top:12px;font-size:13px;color:#a78bfa;font-weight:600">Your coupons</div>'
        + myC.map((c) => `<div class="my-coupon">\u{1F3F7}️ ${c.name} · code <b>${c.code}</b></div>`).join('');
    } else {
      myEl.innerHTML = '';
    }
  } catch (e) {
    // Fallback to localStorage
    console.warn('Coin API failed, using localStorage:', e);
    renderCoinPanelFallback();
  }
}

export function toggleCoinPanel() {
  const panel = document.getElementById('coin-panel');
  const show = panel.classList.contains('hidden');
  panel.classList.toggle('hidden');
  if (show) renderCoinPanel();
}

export function toggleCart() {
  document.getElementById('cart-panel').classList.toggle('hidden');
}

// Keep old coin badge update — use API when possible
export async function updateCoinBadge() {
  try {
    const data = await fetchBalance();
    const el = document.getElementById('coin-balance');
    if (el) el.textContent = data.balance;
  } catch {
    // Fallback
    const el = document.getElementById('coin-balance');
    if (el) el.textContent = getCoins();
  }
}

// ---- Ad video ----
export function openAd() {
  const modal = document.getElementById('ad-modal');
  const video = document.getElementById('ad-video');
  const status = document.getElementById('ad-status');
  if (!modal || !video) return;
  modal.style.display = 'flex';
  status.textContent = 'Playing… watch to the end to earn coins';
  video.src = AD_VIDEO_URL;
  video.currentTime = 0;
  video.muted = false;
  let rewarded = false;
  video.onended = async () => {
    if (rewarded) return;
    rewarded = true;
    try {
      // Earn coins via API
      await earnCoinsAPI(AD_REWARD, 'Ad reward', 'ad');
      await updateCoinBadge();
      status.textContent = `\u{1F389} +${AD_REWARD} coins!`;
    } catch {
      // Fallback
      addCoins(AD_REWARD);
      status.textContent = `\u{1F389} +${AD_REWARD} coins! Balance: ${getCoins()}`;
    }
  };
  video.onerror = () => {
    status.textContent = 'Video failed to load. Check the ad file in frontend/assets/.';
  };
  const p = video.play();
  if (p && p.catch) p.catch(() => {
    status.textContent = 'Tap the video to start playback.';
  });
}
export function closeAd() {
  const modal = document.getElementById('ad-modal');
  const video = document.getElementById('ad-video');
  if (video) { video.pause(); video.removeAttribute('src'); video.load(); }
  if (modal) modal.style.display = 'none';
}

// ---- API-driven actions ----
export async function search(queryText) {
  const input = document.getElementById('query-input');
  const btn = document.getElementById('search-btn');
  btn.disabled = true;
  input.value = '';

  addUserMessage(queryText);
  addTypingIndicator();

  try {
    const data = await recommend(queryText);
    addAIMessage(data.answer, data.products || []);
  } catch (e) {
    addErrorMessage('Search failed: ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

export async function runZoneRecommend(query) {
  addUserMessage(query);
  addTypingIndicator();
  try {
    const data = await recommend(query);
    addAIMessage(data.answer, data.products || []);
  } catch (e) {
    addErrorMessage('Zone recommend failed: ' + e.message);
  }
}

/** Read the saved default full-body photo URL from the current user object. */
function defaultPhotoUrl() {
  let m = getCurrentUser()?.body_measurements;
  if (typeof m === 'string') { try { m = JSON.parse(m); } catch { m = null; } }
  return m?.body_photo_url || null;
}

/** Resolve a person image File: prefer a freshly chosen file, else the saved default full-body photo. */
async function resolvePersonImage() {
  const input = document.getElementById('photo-input');
  if (input?.files?.length) return input.files[0];

  // In-memory user may be stale (photo uploaded elsewhere) → refresh from server once.
  let url = defaultPhotoUrl();
  if (!url) { await fetchMe().catch(() => {}); url = defaultPhotoUrl(); }
  if (!url) return null;

  const abs = /^https?:\/\//i.test(url)
    ? url
    : (API_URL || '').replace(/\/$/, '') + (url.startsWith('/') ? url : '/' + url);
  try {
    const r = await fetch(abs, { credentials: 'include' });
    if (!r.ok) return null;
    const blob = await r.blob();
    let ext = (blob.type && blob.type.split('/')[1]) || 'jpg';
    if (ext === 'jpeg') ext = 'jpg';
    return new File([blob], `default-body.${ext}`, { type: blob.type || 'image/jpeg' });
  } catch { return null; }
}

export async function runTryOn() {
  if (!selectedProduct?.image_url) {
    addErrorMessage('Please select a product first, then try it on.');
    return;
  }
  const personImage = await resolvePersonImage();
  if (!personImage) {
    addErrorMessage('Upload a full-body photo, or set a default one in your profile to skip this step.');
    return;
  }
  const productName = selectedProduct.product_name || 'selected item';
  addUserMessage(`Virtual try-on: ${productName}`);
  addTypingIndicator();
  try {
    const data = await tryOn(
      personImage,
      selectedProduct.image_url,
      selectedProduct.product_name,
      selectedProduct.brand,
      selectedProduct.id
    );
    tryonResult = { url: data.tryon_image_url, base64: data.tryon_image_base64 };
    addAITryOnResultMessage({
      src: resolveTryOnImageSrc(data),
      productName,
      brand: selectedProduct.brand,
    });
    document.getElementById('model-panel').classList.remove('hidden');
    document.getElementById('model-status').textContent = 'Try-on ready. Generate 3D model.';
  } catch (e) {
    addErrorMessage('Try-on failed: ' + e.message);
  }
}

// ---- 3D pipeline helpers (pose → mesh → rig → animation) ----
const STAGE_ORDER = ['pose_normalize', 'mesh', 'rig', 'animation'];
const STAGE_LABEL = {
  pose_normalize: 'T-pose',
  mesh: 'Modeling',
  rig: 'Rigging',
  animation: 'Animating',
};

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

// Reflect current pipeline stage + percentage in the model panel UI.
function setStageProgress(stage, progress, message) {
  const status = document.getElementById('model-status');
  if (status && message != null) status.textContent = message;
  const bar = document.getElementById('stage-progress-bar');
  if (bar) bar.style.width = `${Math.max(0, Math.min(100, progress || 0))}%`;
  const activeIdx = STAGE_ORDER.indexOf(stage);
  document.querySelectorAll('#stage-capsules .stage-capsule').forEach((el) => {
    const idx = STAGE_ORDER.indexOf(el.dataset.stage);
    el.classList.toggle('active', idx === activeIdx);
    el.classList.toggle('done', activeIdx > idx && idx >= 0);
  });
}

// Pick the highest-fidelity GLB available: animation > rig > mesh.
function bestGlbUrl(status) {
  const raw = status.animation?.glb_url || status.rig?.glb_url
    || status.mesh?.glb_url || status.download_url;
  if (!raw) return null;
  if (/^(https?:)?\/\//i.test(raw)) return raw;
  return (API_URL || '').replace(/\/$/, '') + (raw.startsWith('/') ? raw : '/' + raw);
}

async function pollImg2ModelUntilDone(taskId, { interval = 2500, maxAttempts = 120 } = {}) {
  for (let i = 0; i < maxAttempts; i++) {
    const status = await getImg2ModelStatus(taskId);
    setStageProgress(
      status.stage,
      status.progress,
      `${STAGE_LABEL[status.stage] || status.stage}… ${status.progress || 0}%`
    );
    if (status.state === 'done' || status.state === 'failed') return status;
    await sleep(interval);
  }
  throw new Error('Timed out waiting for 3D model generation.');
}

export async function generate3D() {
  if (!tryonResult || (!tryonResult.url && !tryonResult.base64)) {
    addErrorMessage('Complete a virtual try-on first.');
    return;
  }
  const btn = document.getElementById('gen3d-btn');
  const poseNormalize = document.getElementById('pose-toggle')?.checked ?? true;
  const rigEnabled = document.getElementById('rig-toggle')?.checked ?? false;
  const animationEnabled = document.getElementById('anim-toggle')?.checked ?? false;
  const animationPreset = document.getElementById('anim-preset')?.value || 'idle';

  if (btn) btn.disabled = true;
  setStageProgress('pose_normalize', 5, 'Submitting 3D model task…');
  try {
    const { task_id } = await submitImg2Model({
      imageUrl: tryonResult.url,
      imageBase64: tryonResult.base64,
      filenamePrefix: 'tryon_model',
      rigEnabled,
      animationEnabled,
      animationPreset,
      poseNormalize,
      productId: selectedProduct?.id,
    });

    const result = await pollImg2ModelUntilDone(task_id);
    const url = bestGlbUrl(result);

    if (result.state === 'failed') {
      if (url) {
        loadModel(url);
        setStageProgress(result.stage, 100,
          `Stopped at ${STAGE_LABEL[result.stage] || result.stage}: ${result.error || 'error'} — showing best available model.`);
      } else {
        setStageProgress(result.stage, 100, `Failed: ${result.error || 'unknown error'}`);
      }
      return;
    }

    if (!url) {
      setStageProgress(result.stage, 100, 'No model file was produced.');
      return;
    }

    loadModel(url);
    const tier = result.animation?.glb_url ? 'animated'
      : (result.rig?.glb_url ? 'rigged' : 'static');
    setStageProgress(result.stage, 100, `Model loaded (${tier}). Walk to the 3D Showcase zone to view.`);
  } catch (e) {
    setStageProgress('mesh', 100, 'Error: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}
