// ===== localStorage fallback (used only when the API is unavailable) =====
import { COINS_KEY, COUPONS_KEY, COUPON_TIERS } from '/app/shared/config.js';

export function getCoins() {
  const n = parseInt(localStorage.getItem(COINS_KEY) || '0', 10);
  return isNaN(n) ? 0 : n;
}
export function setCoins(n) {
  try { localStorage.setItem(COINS_KEY, String(Math.max(0, n))); } catch {}
}
export function addCoins(n) { setCoins(getCoins() + n); }

export function loadCoupons() {
  try { return JSON.parse(localStorage.getItem(COUPONS_KEY) || '[]'); } catch { return []; }
}
export function saveCoupons(list) {
  try { localStorage.setItem(COUPONS_KEY, JSON.stringify(list)); } catch {}
}

// Cart fallback (in-memory, lost on reload — only a safety net)
const cart = new Map();
function productKey(p) {
  return (p.id && String(p.id)) || (p.farfetch_id && String(p.farfetch_id)) || `${p.product_name || ''}|${p.image_url || ''}`;
}
export function addToCartFallback(product) { cart.set(productKey(product), product); }
export function getCartFallback() { return cart; }
export function clearCartFallback() { cart.clear(); }

export function renderCoinPanelFallback() {
  const balEl = document.getElementById('coin-panel-balance');
  if (balEl) balEl.textContent = getCoins();
  const tiersEl = document.getElementById('coupon-tiers');
  if (!tiersEl) return;
  tiersEl.innerHTML = '';
  COUPON_TIERS.forEach((tier, i) => {
    const row = document.createElement('div');
    row.className = 'coupon-tier';
    const afford = getCoins() >= tier.cost;
    row.innerHTML = `
      <div><div class="info">${tier.label}</div><div class="cost">${tier.cost} \u{1FA99}</div></div>
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
  if (myEl) {
    myEl.innerHTML = mine.length
      ? '<div class="my-coupons-title">Your coupons</div>' +
        mine.map((c) => `<div class="my-coupon">\u{1F3F7}\uFE0F ${c.label} · code <b>${c.code}</b></div>`).join('')
      : '';
  }
}
