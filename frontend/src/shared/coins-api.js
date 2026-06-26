// ===== Coins & Coupons API =====
import { API_URL } from '/app/shared/config.js';
import { authHeaders } from '/app/shared/auth.js';

const COINS_URL = API_URL + '/coins';
const COUPONS_URL = API_URL + '/coupons';

export async function fetchBalance() {
  const r = await fetch(COINS_URL, { credentials: 'include', headers: authHeaders() });
  if (!r.ok) return { balance: 0, total_earned: 0, total_spent: 0 };
  return await r.json();
}

export async function earnCoinsAPI(amount, reason, refType, refId) {
  const r = await fetch(COINS_URL + '/earn', {
    method: 'POST', headers: authHeaders(), credentials: 'include',
    body: JSON.stringify({ amount, reason, reference_type: refType, reference_id: refId }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Failed to earn coins'); }
  return await r.json();
}

export async function spendCoinsAPI(amount, reason, refType, refId) {
  const r = await fetch(COINS_URL + '/spend', {
    method: 'POST', headers: authHeaders(), credentials: 'include',
    body: JSON.stringify({ amount, reason, reference_type: refType, reference_id: refId }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Failed to spend coins'); }
  return await r.json();
}

export async function dailyCheckin() {
  const r = await fetch(COINS_URL + '/checkin', { method: 'POST', headers: authHeaders(), credentials: 'include' });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Check-in failed'); }
  return await r.json();
}

export async function fetchTransactions() {
  const r = await fetch(API_URL + '/users/me/coins/transactions', { credentials: 'include', headers: authHeaders() });
  if (!r.ok) return { balance: 0, transactions: [] };
  return await r.json();
}

export async function fetchAvailableCoupons() {
  const r = await fetch(COUPONS_URL + '/available', { credentials: 'include', headers: authHeaders() });
  if (!r.ok) return { coupons: [] };
  return await r.json();
}

export async function redeemCouponAPI(templateId) {
  const r = await fetch(COUPONS_URL + '/redeem', {
    method: 'POST', headers: authHeaders(), credentials: 'include',
    body: JSON.stringify({ coupon_template_id: templateId }),
  });
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || 'Redeem failed'); }
  return await r.json();
}

export async function fetchMyCoupons() {
  const r = await fetch(COUPONS_URL + '/my', { credentials: 'include', headers: authHeaders() });
  if (!r.ok) return { coupons: [] };
  return await r.json();
}
