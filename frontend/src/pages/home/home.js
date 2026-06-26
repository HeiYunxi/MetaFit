// ===== Home page: product grid + search + category + pagination =====
import { mountNav } from '/app/shared/nav.js';
import { fetchProducts, fetchCategories } from '/app/shared/catalog-api.js';

const state = { q: '', category: '', sort: 'newest', page: 1, pageSize: 24, total: 0 };

const grid = document.getElementById('product-grid');
const meta = document.getElementById('result-meta');
const pager = document.getElementById('pagination');
const chips = document.getElementById('category-chips');
const searchInput = document.getElementById('search-input');

function priceStr(p) {
  if (p.price == null) return '';
  const cur = p.currency || '¥';
  let s = `${cur}${p.price}`;
  if (p.original_price && p.original_price > p.price) {
    s += `<span class="orig">${cur}${p.original_price}</span>`;
  }
  return s;
}

function renderGrid(items) {
  if (!items.length) {
    grid.innerHTML = '<div class="muted" style="grid-column:1/-1;padding:40px;text-align:center">No matching products found.</div>';
    return;
  }
  grid.innerHTML = '';
  items.forEach((p) => {
    const card = document.createElement('div');
    card.className = 'product-card';
    card.innerHTML = `
      ${p.image_url ? `<img class="thumb" src="${p.image_url}" alt="" loading="lazy">` : '<div class="thumb"></div>'}
      <div class="body">
        <div class="brand">${p.brand || ''}</div>
        <div class="name">${p.product_name || 'Product'}</div>
        <div class="price">${priceStr(p)}</div>
      </div>`;
    card.addEventListener('click', () => { location.href = `/product?id=${p.id}`; });
    grid.appendChild(card);
  });
}

function renderPager() {
  const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
  if (pages <= 1) { pager.innerHTML = ''; return; }
  pager.innerHTML = '';
  const mk = (label, page, disabled, active) => {
    const b = document.createElement('button');
    b.textContent = label;
    if (active) b.classList.add('active');
    b.disabled = !!disabled;
    b.addEventListener('click', () => { state.page = page; load(); window.scrollTo({ top: 0, behavior: 'smooth' }); });
    return b;
  };
  pager.appendChild(mk('‹', state.page - 1, state.page <= 1));
  const start = Math.max(1, state.page - 2);
  const end = Math.min(pages, start + 4);
  for (let i = start; i <= end; i++) pager.appendChild(mk(String(i), i, false, i === state.page));
  pager.appendChild(mk('›', state.page + 1, state.page >= pages));
}

async function load() {
  grid.innerHTML = '<div class="muted" style="grid-column:1/-1;padding:40px;text-align:center">Loading…</div>';
  try {
    const data = await fetchProducts(state);
    state.total = data.total;
    meta.textContent = `${data.total} products`;
    renderGrid(data.items || []);
    renderPager();
  } catch (e) {
    grid.innerHTML = `<div class="muted" style="grid-column:1/-1;padding:40px;text-align:center">Failed to load: ${e.message}</div>`;
  }
}

async function loadCategories() {
  const { categories = [] } = await fetchCategories();
  const all = [{ name: '', label: 'All' }, ...categories.map((c) => ({ name: c.name, label: `${c.name} (${c.count})` }))];
  chips.innerHTML = '';
  all.forEach((c) => {
    const chip = document.createElement('button');
    chip.className = 'chip' + (state.category === c.name ? ' active' : '');
    chip.textContent = c.label;
    chip.addEventListener('click', () => {
      state.category = c.name; state.page = 1;
      chips.querySelectorAll('.chip').forEach((x) => x.classList.remove('active'));
      chip.classList.add('active');
      load();
    });
    chips.appendChild(chip);
  });
}

function bindToolbar() {
  const doSearch = () => { state.q = searchInput.value.trim(); state.page = 1; load(); };
  document.getElementById('search-btn').addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
  document.getElementById('sort-select').addEventListener('change', (e) => { state.sort = e.target.value; state.page = 1; load(); });
}

mountNav({ active: 'home', showFittingRoom: true, showCart: true });
bindToolbar();
loadCategories();
load();
