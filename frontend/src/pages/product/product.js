// ===== Product detail page =====
import { mountNav, refreshCartCount, openCartDrawer } from '/app/shared/nav.js';
import { fetchProduct, recordView } from '/app/shared/catalog-api.js';
import { addToCartAPI } from '/app/shared/cart-api.js';

const params = new URLSearchParams(location.search);
const productId = parseInt(params.get('id'), 10);
const detailEl = document.getElementById('product-detail');
let selectedSize = null;

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 1800);
}

function priceBlock(p) {
  const cur = p.currency || '¥';
  let s = `<div class="pd-price">${cur}${p.price}`;
  if (p.original_price && p.original_price > p.price) s += `<span class="pd-orig">${cur}${p.original_price}</span>`;
  s += '</div>';
  return s;
}

function specRows(p) {
  const rows = [
    ['Category', p.label], ['Brand', p.brand],
    ['Outer Material', p.composition_outer], ['Lining Material', p.composition_lining],
    ['Care', p.washing_instructions], ['Model Info', p.model_info],
  ].filter(([, v]) => v);
  if (!rows.length) return '';
  return `<div class="pd-section"><h3>Specifications</h3><table class="spec-table">${
    rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table></div>`;
}

function render({ product: p, sizes, similar }) {
  document.title = `${p.product_name} — MateFit`;
  const sizeHtml = sizes && sizes.length
    ? `<div class="pd-section"><h3>Sizes</h3><div class="size-list">${
        sizes.map((s) => `<button class="size-pill ${s.stock_status === 'out_of_stock' ? 'out' : ''}" data-size="${s.size_label}" ${s.stock_status === 'out_of_stock' ? 'disabled' : ''}>${s.size_label}</button>`).join('')
      }</div></div>`
    : '';

  detailEl.innerHTML = `
    <div>${p.image_url ? `<img class="pd-image" src="${p.image_url}" alt="">` : '<div class="pd-image"></div>'}</div>
    <div class="pd-info">
      <div class="pd-brand">${p.brand || ''}</div>
      <h1>${p.product_name}</h1>
      ${priceBlock(p)}
      ${sizeHtml}
      ${p.description ? `<div class="pd-section"><h3>Description</h3><div class="pd-desc">${p.description}</div></div>` : ''}
      ${specRows(p)}
      <div class="pd-actions">
        <button class="btn-primary" id="add-cart-btn">🛒 Add to Cart</button>
        <button class="btn-secondary" id="tryon-btn">👗 Try in Fitting Room</button>
      </div>
    </div>`;

  detailEl.querySelectorAll('.size-pill').forEach((pill) => {
    pill.addEventListener('click', () => {
      if (pill.classList.contains('out')) return;
      detailEl.querySelectorAll('.size-pill').forEach((x) => x.classList.remove('active'));
      pill.classList.add('active');
      selectedSize = pill.dataset.size;
    });
  });

  document.getElementById('add-cart-btn').addEventListener('click', async () => {
    try {
      await addToCartAPI(p.id, selectedSize, 1);
      await refreshCartCount();
      toast('Added to cart');
      openCartDrawer();
    } catch (e) { toast('Failed to add: ' + e.message); }
  });

  document.getElementById('tryon-btn').addEventListener('click', () => {
    location.href = `/fitting-room?product=${p.id}`;
  });

  // Similar
  if (similar && similar.length) {
    const sec = document.getElementById('similar-section');
    const sg = document.getElementById('similar-grid');
    sec.classList.remove('hidden');
    sg.innerHTML = '';
    similar.forEach((s) => {
      const card = document.createElement('div');
      card.className = 'product-card';
      card.innerHTML = `
        ${s.image_url ? `<img class="thumb" src="${s.image_url}" alt="" loading="lazy">` : '<div class="thumb"></div>'}
        <div class="body"><div class="brand">${s.brand || ''}</div><div class="name">${s.product_name}</div>
        <div class="price">${s.currency || '¥'}${s.price}</div></div>`;
      card.addEventListener('click', () => { location.href = `/product?id=${s.id}`; });
      sg.appendChild(card);
    });
  }
}

async function init() {
  await mountNav({ active: '', showFittingRoom: true, showCart: true });
  if (!productId) { detailEl.innerHTML = '<div class="muted" style="padding:40px">Invalid product ID.</div>'; return; }
  try {
    const data = await fetchProduct(productId);
    render(data);
    recordView(productId);
  } catch (e) {
    detailEl.innerHTML = `<div class="muted" style="padding:40px">${e.message}</div>`;
  }
}

init();
