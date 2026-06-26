// ===== Shared top navigation bar + cart drawer (for 2D pages) =====
import { initAuth, onAuthChange, isLoggedIn, isMerchant, getCurrentUser, logout } from '/app/shared/auth.js';
import { openAuthModal } from '/app/shared/auth-ui.js';
import { fetchCart, removeFromCartAPI, clearCartAPI } from '/app/shared/cart-api.js';

/**
 * Render the shared navigation bar into <header id="app-nav">.
 * opts: { active: 'home'|'fitting'|'profile', showFittingRoom, showCart }
 */
export async function mountNav(opts = {}) {
  const { active = '', showFittingRoom = true, showCart = true } = opts;
  let header = document.getElementById('app-nav');
  if (!header) {
    header = document.createElement('header');
    header.id = 'app-nav';
    document.body.prepend(header);
  }
  header.innerHTML = `
    <a class="nav-logo" href="/MetaClothesShop">Mate<span>Fit</span></a>
    <nav class="nav-actions">
      ${showFittingRoom ? `<a class="nav-link ${active === 'fitting' ? 'active' : ''}" href="/fitting-room">\u{1F454} Fitting Room</a>` : ''}
      ${showCart ? `<button class="nav-link nav-cart" id="nav-cart-btn">\u{1F6D2} <span id="nav-cart-count">0</span></button>` : ''}
      <button class="nav-link nav-profile" id="nav-profile-btn">\u{1F464} Profile</button>
      <span id="nav-auth"></span>
    </nav>`;

  // Profile button: requires login
  header.querySelector('#nav-profile-btn').addEventListener('click', async () => {
    if (isLoggedIn()) { location.href = '/profile'; return; }
    const ok = await openAuthModal();
    if (ok) location.href = '/profile';
  });

  if (showCart) {
    buildCartDrawer();
    header.querySelector('#nav-cart-btn').addEventListener('click', openCartDrawer);
  }

  // Auth state (login button / username dropdown)
  onAuthChange((user) => renderAuthArea(header, user, showCart));

  await initAuth();
  if (showCart) refreshCartCount();
}

function renderAuthArea(header, user, showCart) {
  const el = header.querySelector('#nav-auth');
  if (!el) return;
  if (user) {
    el.innerHTML = `
      <span class="nav-user" id="nav-user">${user.username} \u25be</span>
      <div class="nav-menu hidden" id="nav-menu">
        <a href="/profile">\u{1F464} Profile</a>
        ${isMerchant() ? '<a href="/merchant">\u{1F3EA} Merchant Portal</a>' : ''}
        <a href="#" id="nav-logout">\u{1F6AA} Logout</a>
      </div>`;
    const menu = el.querySelector('#nav-menu');
    el.querySelector('#nav-user').addEventListener('click', (e) => { e.stopPropagation(); menu.classList.toggle('hidden'); });
    el.querySelector('#nav-logout').addEventListener('click', async (e) => { e.preventDefault(); await logout(); location.reload(); });
    document.addEventListener('click', () => menu.classList.add('hidden'));
  } else {
    el.innerHTML = `<button class="nav-link nav-login" id="nav-login-btn">\u{1F512} Login</button>`;
    el.querySelector('#nav-login-btn').addEventListener('click', async () => {
      const ok = await openAuthModal();
      if (ok && showCart) refreshCartCount();
    });
  }
}

// ---- Cart drawer ----
let drawer = null;
function buildCartDrawer() {
  if (drawer) return;
  drawer = document.createElement('div');
  drawer.id = 'cart-drawer';
  drawer.className = 'cart-drawer';
  drawer.innerHTML = `
    <div class="cart-drawer-backdrop"></div>
    <aside class="cart-drawer-panel">
      <div class="cart-drawer-head"><h3>\u{1F6D2} Cart</h3><button id="cart-drawer-close">\u2715</button></div>
      <div id="cart-drawer-items" class="cart-drawer-items"></div>
      <div class="cart-drawer-foot">
        <button id="cart-drawer-clear" class="btn-secondary">Clear</button>
        <button id="cart-drawer-checkout" class="btn-primary">Checkout</button>
      </div>
    </aside>`;
  document.body.appendChild(drawer);
  drawer.querySelector('.cart-drawer-backdrop').addEventListener('click', closeCartDrawer);
  drawer.querySelector('#cart-drawer-close').addEventListener('click', closeCartDrawer);
  drawer.querySelector('#cart-drawer-clear').addEventListener('click', async () => { await clearCartAPI().catch(() => {}); renderCartDrawer(); });
  drawer.querySelector('#cart-drawer-checkout').addEventListener('click', () => alert('Checkout flow coming soon.'));
}

async function openCartDrawer() { buildCartDrawer(); drawer.classList.add('open'); await renderCartDrawer(); }
function closeCartDrawer() { if (drawer) drawer.classList.remove('open'); }

async function renderCartDrawer() {
  const box = drawer.querySelector('#cart-drawer-items');
  box.innerHTML = '<div class="muted">Loading…</div>';
  try {
    const { items = [] } = await fetchCart();
    setCartCount(items.length);
    if (!items.length) { box.innerHTML = '<div class="muted">Your cart is empty.</div>'; return; }
    box.innerHTML = '';
    items.forEach((it) => {
      const row = document.createElement('div');
      row.className = 'cart-row';
      const price = it.price ? `${it.currency || '¥'}${it.price}` : '';
      row.innerHTML = `
        ${it.image_url ? `<img src="${it.image_url}" alt="">` : '<div class="ph"></div>'}
        <div class="cart-row-info"><div class="nm">${it.product_name || 'Product'}</div><div class="pr">${price}</div></div>
        <button class="cart-row-rm">Remove</button>`;
      row.querySelector('.cart-row-rm').addEventListener('click', async () => { await removeFromCartAPI(it.id).catch(() => {}); renderCartDrawer(); });
      box.appendChild(row);
    });
  } catch {
    box.innerHTML = '<div class="muted">Cart unavailable.</div>';
  }
}

async function refreshCartCount() {
  try { const { items = [] } = await fetchCart(); setCartCount(items.length); } catch {}
}
function setCartCount(n) {
  const el = document.getElementById('nav-cart-count');
  if (el) el.textContent = n;
}

export { refreshCartCount, openCartDrawer };
