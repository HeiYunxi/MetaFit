// ===== Product List Page =====
import { fetchProducts, deleteProduct } from './merchant-api.js';

let currentPage = 1;
let currentSearch = '';
let currentLabel = '';

async function init() {
  window._initProductList = loadProducts;

  document.getElementById('search-btn')?.addEventListener('click', () => {
    currentSearch = document.getElementById('search-input')?.value || '';
    currentLabel = document.getElementById('label-filter')?.value || '';
    currentPage = 1;
    loadProducts();
  });

  // Enter key in search
  document.getElementById('search-input')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      currentSearch = e.target.value;
      currentLabel = document.getElementById('label-filter')?.value || '';
      currentPage = 1;
      loadProducts();
    }
  });

  loadProducts();
}

async function loadProducts() {
  try {
    const data = await fetchProducts(currentPage, currentSearch, currentLabel);
    const tbody = document.getElementById('product-tbody');
    if (!tbody) return;

    if (!data.items.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#666;padding:40px">No products found. Create your first product!</td></tr>';
    } else {
      tbody.innerHTML = data.items.map(p => `
        <tr>
          <td>${p.image_url ? `<img src="${p.image_url}" style="width:48px;height:60px;object-fit:cover;border-radius:6px">` : '<div style="width:48px;height:60px;background:#2a2a4a;border-radius:6px"></div>'}</td>
          <td>${p.product_name || '—'}</td>
          <td>${p.brand || '—'}</td>
          <td>${p.label || '—'}</td>
          <td>¥${p.price || 0}</td>
          <td><span class="${p.is_active ? 'badge-active' : 'badge-inactive'}">${p.is_active ? 'Active' : 'Hidden'}</span></td>
          <td>
            <button class="btn-secondary edit-btn" data-id="${p.id}" style="padding:4px 8px;font-size:12px;margin-right:4px">Edit</button>
            <button class="btn-secondary delete-btn" data-id="${p.id}" data-name="${p.product_name}" style="padding:4px 8px;font-size:12px;color:#f87171">Del</button>
          </td>
        </tr>
      `).join('');

      // Bind edit
      tbody.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          window._editProductId = parseInt(btn.dataset.id);
          window._navigate('product-edit');
        });
      });

      // Bind delete
      tbody.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          if (confirm(`Deactivate "${btn.dataset.name}"?`)) {
            await deleteProduct(parseInt(btn.dataset.id));
            loadProducts();
          }
        });
      });
    }

    // Pagination
    const totalPages = Math.ceil(data.total / data.page_size);
    document.getElementById('pagination').innerHTML = totalPages > 1
      ? `<button class="btn-secondary" style="padding:4px 12px;font-size:12px" ${currentPage <= 1 ? 'disabled' : ''}>Prev</button>
         <span style="margin:0 12px">Page ${currentPage} / ${totalPages}</span>
         <button class="btn-secondary" style="padding:4px 12px;font-size:12px" ${currentPage >= totalPages ? 'disabled' : ''}>Next</button>`
      : `Page 1 / 1 · ${data.total} products`;

  } catch (e) {
    console.error('Failed to load products:', e);
  }
}

init();
