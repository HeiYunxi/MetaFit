// ===== Catalog API: public product list / detail / view tracking =====
import { API_URL } from '/app/shared/config.js';
import { authHeaders } from '/app/shared/auth.js';

const PRODUCTS_URL = API_URL + '/products';

/** List products with search / category / brand / sort / pagination. */
export async function fetchProducts({ q = '', category = '', brand = '', sort = 'newest', page = 1, pageSize = 24 } = {}) {
  const params = new URLSearchParams({ sort, page: String(page), page_size: String(pageSize) });
  if (q) params.set('q', q);
  if (category) params.set('category', category);
  if (brand) params.set('brand', brand);
  const r = await fetch(`${PRODUCTS_URL}?${params.toString()}`, { credentials: 'include' });
  if (!r.ok) throw new Error('Failed to load products');
  return await r.json();  // { total, page, page_size, items }
}

/** Distinct categories with counts. */
export async function fetchCategories() {
  const r = await fetch(`${PRODUCTS_URL}/categories`, { credentials: 'include' });
  if (!r.ok) return { categories: [] };
  return await r.json();
}

/** Single product detail (+ sizes + similar). */
export async function fetchProduct(id) {
  const r = await fetch(`${PRODUCTS_URL}/${id}`, { credentials: 'include' });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || 'Product not found');
  }
  return await r.json();  // { product, sizes, similar }
}

/** Record a product view (best-effort, used for browse history). */
export async function recordView(id) {
  try {
    await fetch(`${PRODUCTS_URL}/${id}/view`, {
      method: 'POST',
      headers: authHeaders(),
      credentials: 'include',
    });
  } catch {}
}
