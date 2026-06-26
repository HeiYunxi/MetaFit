// ===== Personal homepage (profile) — requires login =====
import { mountNav } from '/app/shared/nav.js';
import { initAuth, isLoggedIn, getCurrentUser } from '/app/shared/auth.js';
import { openAuthModal } from '/app/shared/auth-ui.js';
import {
  getProfile, updateProfile, updateMeasurements,
  getOrders, getBrowseHistory, getChatHistory,
  getTryonHistory, get3dHistory, getMyCoupons, uploadBodyPhoto,
} from '/app/shared/users-api.js';
import { fetchBalance, fetchTransactions, fetchAvailableCoupons, redeemCouponAPI, dailyCheckin } from '/app/shared/coins-api.js';

const content = document.getElementById('profile-content');

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1800);
}
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmtDate = (s) => (s ? String(s).slice(0, 16).replace('T', ' ') : '—');

// ---------- Tab: Profile ----------
async function renderInfo() {
  content.innerHTML = '<div class="muted">Loading…</div>';
  const { user } = await getProfile();
  let m = user.body_measurements || {};
  if (typeof m === 'string') { try { m = JSON.parse(m); } catch { m = {}; } }

  content.innerHTML = `
    <h2>Profile</h2>
    <div class="field-grid">
      <div class="field"><label>Username</label><input id="f-username" value="${esc(user.username)}"></div>
      <div class="field"><label>Email</label><input id="f-email" value="${esc(user.email || '')}"></div>
      <div class="field"><label>Gender</label>
        <select id="f-gender">
          ${['prefer_not_to_say', 'female', 'male', 'other'].map((g) => `<option value="${g}" ${user.gender === g ? 'selected' : ''}>${g}</option>`).join('')}
        </select>
      </div>
      <div class="field"><label>Role</label><input value="${esc(user.role)}" disabled></div>
    </div>
    <div class="form-actions"><button class="btn-primary" id="save-info">Save Profile</button><span class="save-hint" id="info-hint"></span></div>

    <h2 style="margin-top:28px">Default Full-Body Photo</h2>
    <p class="muted" style="margin:-6px 0 12px">Upload a full-body photo to use as the default base image when you enter the Fitting Room.</p>
    <div style="display:flex;align-items:flex-start;gap:20px;flex-wrap:wrap">
      <div id="photo-preview" style="width:160px;height:213px;border-radius:10px;border:1px solid #2a2a4a;background:#12122a;display:flex;align-items:center;justify-content:center;overflow:hidden">
        ${m.body_photo_url
          ? `<img src="${esc(m.body_photo_url)}" alt="full-body" style="width:100%;height:100%;object-fit:cover">`
          : '<span class="muted" style="font-size:12px">No photo yet</span>'}
      </div>
      <div>
        <input type="file" id="photo-file" accept="image/jpeg,image/png,image/webp" style="font-size:13px">
        <div class="form-actions" style="margin-top:10px">
          <button class="btn-primary" id="upload-photo">Upload Photo</button>
          <span class="save-hint" id="photo-hint"></span>
        </div>
      </div>
    </div>

    <h2 style="margin-top:28px">Body Measurements</h2>
    <div class="field-grid">
      <div class="field"><label>Height (cm)</label><input id="m-height" type="number" value="${m.height_cm ?? ''}"></div>
      <div class="field"><label>Weight (kg)</label><input id="m-weight" type="number" value="${m.weight_kg ?? ''}"></div>
      <div class="field"><label>Usual Size</label><input id="m-size" value="${esc(m.usual_size || '')}"></div>
      <div class="field"><label>Shoulder (cm)</label><input id="m-shoulder" type="number" value="${m.shoulder_width_cm ?? ''}"></div>
      <div class="field"><label>Chest (cm)</label><input id="m-chest" type="number" value="${m.chest_cm ?? ''}"></div>
      <div class="field"><label>Waist (cm)</label><input id="m-waist" type="number" value="${m.waist_cm ?? ''}"></div>
      <div class="field"><label>Hip (cm)</label><input id="m-hip" type="number" value="${m.hip_cm ?? ''}"></div>
    </div>
    <div class="form-actions"><button class="btn-primary" id="save-meas">Save Measurements</button><span class="save-hint" id="meas-hint"></span></div>`;

  document.getElementById('save-info').addEventListener('click', async () => {
    try {
      await updateProfile({
        username: document.getElementById('f-username').value.trim(),
        email: document.getElementById('f-email').value.trim(),
        gender: document.getElementById('f-gender').value,
      });
      document.getElementById('info-hint').textContent = 'Saved';
    } catch (e) { toast(e.message); }
  });

  document.getElementById('upload-photo').addEventListener('click', async () => {
    const fileInput = document.getElementById('photo-file');
    const hint = document.getElementById('photo-hint');
    if (!fileInput.files?.length) { hint.textContent = 'Please choose an image first'; return; }
    hint.textContent = 'Uploading…';
    try {
      const { body_photo_url } = await uploadBodyPhoto(fileInput.files[0]);
      const preview = document.getElementById('photo-preview');
      preview.innerHTML = `<img src="${esc(body_photo_url)}" alt="full-body" style="width:100%;height:100%;object-fit:cover">`;
      hint.textContent = 'Uploaded';
      try {
        const u = getCurrentUser();
        if (u) {
          let mm = u.body_measurements;
          if (typeof mm === 'string') { try { mm = JSON.parse(mm); } catch { mm = {}; } }
          u.body_measurements = { ...(mm || {}), body_photo_url };
        }
      } catch {}
    } catch (e) { hint.textContent = ''; toast(e.message); }
  });

  document.getElementById('save-meas').addEventListener('click', async () => {
    const num = (id) => { const v = document.getElementById(id).value; return v === '' ? null : parseFloat(v); };
    try {
      await updateMeasurements({
        height_cm: num('m-height'), weight_kg: num('m-weight'),
        usual_size: document.getElementById('m-size').value.trim() || null,
        shoulder_width_cm: num('m-shoulder'), chest_cm: num('m-chest'),
        waist_cm: num('m-waist'), hip_cm: num('m-hip'),
      });
      document.getElementById('meas-hint').textContent = 'Saved';
    } catch (e) { toast(e.message); }
  });
}

// ---------- Tab: Orders ----------
async function renderOrders() {
  content.innerHTML = '<h2>My Orders</h2><div class="muted">Loading…</div>';
  const { items = [] } = await getOrders();
  if (!items.length) { content.innerHTML = '<h2>My Orders</h2><div class="empty">No orders yet.</div>'; return; }
  content.innerHTML = `<h2>My Orders</h2>
    <table class="list-table"><thead><tr><th>Order No.</th><th>Total</th><th>Paid</th><th>Status</th><th>Time</th></tr></thead>
    <tbody>${items.map((o) => `<tr>
      <td>${esc(o.order_no)}</td><td>¥${o.total_amount}</td><td>¥${o.final_amount}</td>
      <td><span class="badge">${esc(o.status)}</span></td><td>${fmtDate(o.created_at)}</td></tr>`).join('')}</tbody></table>`;
}

// ---------- Tab: Browsing History ----------
async function renderBrowse() {
  content.innerHTML = '<h2>Browsing History</h2><div class="muted">Loading…</div>';
  const { items = [] } = await getBrowseHistory();
  if (!items.length) { content.innerHTML = '<h2>Browsing History</h2><div class="empty">No browsing records yet.</div>'; return; }
  content.innerHTML = `<h2>Browsing History</h2><div class="mini-grid">${items.map((p) => `
    <div class="mini-card" data-id="${p.product_id}">
      ${p.image_url ? `<img src="${esc(p.image_url)}" alt="">` : '<img>'}
      <div class="mc-body"><div class="mc-name">${esc(p.product_name)}</div>
      <div class="mc-sub">${esc(p.brand || '')} · ¥${p.price}</div></div></div>`).join('')}</div>`;
  content.querySelectorAll('.mini-card').forEach((c) => c.addEventListener('click', () => { location.href = `/product?id=${c.dataset.id}`; }));
}

// ---------- Tab: Conversations ----------
async function renderChat() {
  content.innerHTML = '<h2>Conversations</h2><div class="muted">Loading…</div>';
  const { items = [] } = await getChatHistory();
  if (!items.length) { content.innerHTML = '<h2>Conversations</h2><div class="empty">No conversations yet. Chat with the AI in the Fitting Room.</div>'; return; }
  content.innerHTML = `<h2>Conversations</h2>${items.map((c) => `
    <div class="chat-item"><div class="chat-q">💬 ${esc(c.query || '(no query)')}</div>
    <div class="chat-time">${fmtDate(c.created_at)}</div></div>`).join('')}`;
}

// ---------- Tab: Generation History ----------
function bestGlb(m) {
  return m.anim_glb_url || m.rig_glb_url || m.mesh_glb_url || '';
}

// Resolve a try-on result image src: prefer the saved file URL, fall back to stored base64.
function tryonImageSrc(t) {
  if (t.result_image_url) return esc(t.result_image_url);
  const b64 = t.result_image_base64;
  if (!b64) return '';
  return b64.startsWith('data:') ? b64 : `data:image/png;base64,${b64}`;
}

async function renderGen() {
  content.innerHTML = '<h2>Generation History</h2><div class="muted">Loading…</div>';
  const [tryons, models] = await Promise.all([getTryonHistory().catch(() => ({ items: [] })), get3dHistory().catch(() => ({ items: [] }))]);
  const tItems = tryons.items || [];
  const mItems = models.items || [];
  let html = '<h2>Generation History</h2>';
  html += '<div class="section-sub">👗 Virtual Try-On</div>';
  html += tItems.length
    ? `<div class="mini-grid">${tItems.map((t) => { const src = tryonImageSrc(t); return `<div class="mini-card">
        ${src ? `<img src="${src}" alt="">` : '<img>'}
        <div class="mc-body"><div class="mc-name">${esc(t.product_name || 'Try-on result')}</div>
        <div class="mc-sub">${t.success ? 'Success' : 'Failed'} · ${fmtDate(t.created_at)}</div></div></div>`; }).join('')}</div>`
    : '<div class="empty">No try-on records yet.</div>';
  html += '<div class="section-sub">🧊 3D Models</div>';
  html += mItems.length
    ? `<table class="list-table"><thead><tr><th>Product</th><th>Status</th><th>Progress</th><th>Animation</th><th>Time</th><th></th></tr></thead>
       <tbody>${mItems.map((m, i) => `<tr data-row="${i}" class="${bestGlb(m) ? 'row-clickable' : ''}">
       <td>${esc(m.product_name || '—')}</td><td><span class="badge">${esc(m.status)}</span></td>
       <td>${m.progress ?? 0}%</td><td>${esc(m.animation_preset || '—')}</td><td>${fmtDate(m.created_at)}</td>
       <td>${bestGlb(m) ? '<span class="link-go">View in Fitting Room ›</span>' : ''}</td></tr>`).join('')}</tbody></table>`
    : '<div class="empty">No 3D model records yet.</div>';
  content.innerHTML = html;

  content.querySelectorAll('tr[data-row]').forEach((tr) => {
    const m = mItems[Number(tr.dataset.row)];
    const glb = bestGlb(m);
    if (!glb) return;
    tr.addEventListener('click', () => {
      const params = new URLSearchParams();
      params.set('model', glb);
      if (m.session_id) params.set('session', m.session_id);
      if (m.product_id) params.set('product', m.product_id);
      location.href = `/fitting-room?${params.toString()}`;
    });
  });
}

// ---------- Tab: Coupons & Coins ----------
async function renderCoupons() {
  content.innerHTML = '<h2>Coupons & Coins</h2><div class="muted">Loading…</div>';
  const [bal, txns, myC, avail] = await Promise.all([
    fetchBalance(), fetchTransactions().catch(() => ({ transactions: [] })),
    getMyCoupons().catch(() => ({ coupons: [] })), fetchAvailableCoupons().catch(() => ({ coupons: [] })),
  ]);
  const tiers = avail.coupons || [];
  const mine = myC.coupons || [];
  const txs = txns.transactions || [];

  content.innerHTML = `
    <h2>Coupons & Coins</h2>
    <div class="coin-summary">
      <div class="coin-stat"><div class="v">${bal.balance}</div><div class="l">Balance</div></div>
      <div class="coin-stat"><div class="v">${bal.total_earned}</div><div class="l">Total Earned</div></div>
      <div class="coin-stat"><div class="v">${bal.total_spent}</div><div class="l">Total Spent</div></div>
    </div>
    <div class="form-actions"><button class="btn-secondary" id="checkin-btn">📅 Daily Check-in +10</button><span class="save-hint" id="checkin-hint"></span></div>

    <div class="section-sub">Redeemable Coupons</div>
    <div id="tier-list">${tiers.length ? '' : '<div class="empty">No coupons available to redeem.</div>'}</div>

    <div class="section-sub">My Coupons</div>
    <div id="my-list">${mine.length
      ? mine.map((c) => `<div class="my-coupon">🎟️ ${esc(c.name)} · code <b>${esc(c.code || '-')}</b> · until ${fmtDate(c.expires_at)}</div>`).join('')
      : '<div class="empty">No coupons yet.</div>'}</div>

    <div class="section-sub">Coin Transactions</div>
    ${txs.length
      ? `<table class="list-table"><thead><tr><th>Change</th><th>Reason</th><th>Balance</th><th>Time</th></tr></thead>
         <tbody>${txs.map((t) => `<tr><td style="color:${t.amount >= 0 ? 'var(--green)' : 'var(--danger)'}">${t.amount >= 0 ? '+' : ''}${t.amount}</td>
         <td>${esc(t.reason)}</td><td>${t.balance_after}</td><td>${fmtDate(t.created_at)}</td></tr>`).join('')}</tbody></table>`
      : '<div class="empty">No transactions yet.</div>'}`;

  const tierBox = document.getElementById('tier-list');
  tiers.forEach((t) => {
    const cost = t.discount_type === 'fixed' ? Math.max(1, Math.round(t.discount_value)) : Math.max(1, Math.round(t.max_discount_amount || 50));
    const row = document.createElement('div');
    row.className = 'coupon-tier';
    row.innerHTML = `<div><div class="info">${esc(t.name)}</div>
      <div class="cost">${t.discount_type === 'fixed' ? `¥${t.discount_value} coupon` : `${t.discount_value * 100}% off`} · costs ${cost} 🪙</div></div>
      <button class="btn-secondary" ${bal.balance >= cost ? '' : 'disabled'}>Redeem</button>`;
    row.querySelector('button').addEventListener('click', async () => {
      try { await redeemCouponAPI(t.id); toast('Redeemed'); renderCoupons(); }
      catch (e) { toast(e.message); }
    });
    tierBox.appendChild(row);
  });

  document.getElementById('checkin-btn').addEventListener('click', async () => {
    try { const r = await dailyCheckin(); document.getElementById('checkin-hint').textContent = r.message || 'Checked in'; renderCoupons(); }
    catch (e) { toast(e.message); }
  });
}

const RENDERERS = { info: renderInfo, orders: renderOrders, browse: renderBrowse, chat: renderChat, gen: renderGen, coupons: renderCoupons };

function bindTabs() {
  document.querySelectorAll('.ptab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.ptab').forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      const fn = RENDERERS[tab.dataset.tab];
      if (fn) fn().catch((e) => { content.innerHTML = `<div class="empty">Failed to load: ${esc(e.message)}</div>`; });
    });
  });
}

async function init() {
  await mountNav({ active: 'profile', showFittingRoom: true, showCart: true });
  await initAuth();
  if (!isLoggedIn()) {
    const ok = await openAuthModal();
    if (!ok || !isLoggedIn()) { location.href = '/MetaClothesShop'; return; }
  }
  bindTabs();
  renderInfo().catch((e) => { content.innerHTML = `<div class="empty">Failed to load: ${esc(e.message)}</div>`; });
}

init();
