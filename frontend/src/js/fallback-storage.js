// ===== localStorage fallback: used when API is unavailable =====
// Kept for backward compatibility during migration period.

import { COINS_KEY, COUPONS_KEY, COUPON_TIERS } from './config.js';

// ---- Coins ----
export function getCoins() {
  const n = parseInt(localStorage.getItem(COINS_KEY) || '0', 10);
  return isNaN(n) ? 0 : n;
}
export function setCoins(n) {
  try { localStorage.setItem(COINS_KEY, String(Math.max(0, n))); } catch {}
}
export function addCoins(n) { setCoins(getCoins() + n); }

// ---- Coupons ----
export function loadCoupons() {
  try { return JSON.parse(localStorage.getItem(COUPONS_KEY) || '[]'); } catch { return []; }
}
export function saveCoupons(list) {
  try { localStorage.setItem(COUPONS_KEY, JSON.stringify(list)); } catch {}
}

// ---- Cart (fallback) ----
const cart = new Map();
function productKey(p) {
  return (p.farfetch_id && String(p.farfetch_id)) || `${p.product_name || ''}|${p.image_url || ''}`;
}
export function addToCartFallback(product) {
  cart.set(productKey(product), product);
}
export function getCartFallback() {
  return cart;
}
export function clearCartFallback() {
  cart.clear();
}

// ---- Coin panel fallback ----
export function renderCoinPanelFallback() {
  document.getElementById('coin-panel-balance').textContent = getCoins();
  const tiersEl = document.getElementById('coupon-tiers');
  tiersEl.innerHTML = '';
  COUPON_TIERS.forEach((tier, i) => {
    const row = document.createElement('div');
    row.className = 'coupon-tier';
    const afford = getCoins() >= tier.cost;
    row.innerHTML = `
      <div>
        <div class="info">${tier.label}</div>
        <div class="cost">${tier.cost} \u{1FA99}</div>
      </div>
      <button data-tier="${i}" ${afford ? '' : 'disabled'}>Redeem</button>`;
    row.querySelector('button').addEventListener('click', () => {
      if (getCoins() < tier.cost) return;
      setCoins(getCoins() - tier.cost);
      const mine = loadCoupons();
      mine.push({ label: tier.label, code: tier.code });
      saveCoupons(mine);
      renderCoinPanelFallback();
    });
    tiersEl.appendChild(row);
  });
  const mine = loadCoupons();
  const myEl = document.getElementById('my-coupons');
  if (mine.length) {
    myEl.innerHTML = '<div style="margin-top:12px;font-size:13px;color:#a78bfa;font-weight:600">Your coupons</div>'
      + mine.map((c) => `<div class="my-coupon">\u{1F3F7}️ ${c.label} · code <b>${c.code}</b></div>`).join('');
  } else {
    myEl.innerHTML = '';
  }
}
