// ===== Cart API (server-side, session/user scoped) =====
import { API_URL } from '/app/shared/config.js';
import { authHeaders } from '/app/shared/auth.js';

const CART_URL = API_URL + '/cart';

export async function fetchCart() {
  const r = await fetch(CART_URL, { credentials: 'include', headers: authHeaders() });
  if (!r.ok) throw new Error('Failed to fetch cart');
  return await r.json();  // { items, count }
}

export async function addToCartAPI(productId, selectedSize, quantity = 1) {
  const r = await fetch(CART_URL, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'include',
    body: JSON.stringify({ product_id: productId, selected_size: selectedSize, quantity }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to add to cart');
  }
  return await r.json();
}

export async function removeFromCartAPI(itemId) {
  const r = await fetch(`${CART_URL}/${itemId}`, {
    method: 'DELETE', headers: authHeaders(), credentials: 'include',
  });
  if (!r.ok) throw new Error('Failed to remove from cart');
  return await r.json();
}

export async function clearCartAPI() {
  const r = await fetch(CART_URL, {
    method: 'DELETE', headers: authHeaders(), credentials: 'include',
  });
  if (!r.ok) throw new Error('Failed to clear cart');
  return await r.json();
}
