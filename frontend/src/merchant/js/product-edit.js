// ===== Product Edit Page =====
import { fetchProduct, createProduct, updateProduct, updateSizes, uploadImage } from './merchant-api.js';

const SIZE_OPTIONS = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', 'One Size'];
const STOCK_OPTIONS = ['in_stock', 'low_stock', 'out_of_stock', 'unknown'];

let editingProductId = null;
let currentSizes = [];  // [{size_label, size_category, stock_status}]
let uploadedImageUrl = '';

async function init() {
  document.getElementById('back-to-list')?.addEventListener('click', () => {
    editingProductId = null;
    window._editProductId = null;
    resetForm();
    window._navigate('products');
  });

  document.getElementById('save-product-btn')?.addEventListener('click', saveProduct);
  document.getElementById('add-size-btn')?.addEventListener('click', addSizeRow);
  document.getElementById('image-upload')?.addEventListener('change', handleImageUpload);

  // Watch for navigation to this page
  const observer = new MutationObserver(() => {
    const page = document.getElementById('page-product-edit');
    if (page && page.classList.contains('active')) {
      if (window._editProductId) {
        loadProduct(window._editProductId);
      }
    }
  });
  observer.observe(document.getElementById('content'), { attributes: false, childList: true, subtree: false });
}

function resetForm() {
  const form = document.getElementById('product-form');
  if (form) form.reset();
  currentSizes = [];
  uploadedImageUrl = '';
  document.getElementById('edit-title').textContent = 'New Product';
  renderSizes();
}

async function loadProduct(id) {
  try {
    const data = await fetchProduct(id);
    const p = data.product;
    editingProductId = p.id;
    document.getElementById('edit-title').textContent = `Edit: ${p.product_name}`;

    const form = document.getElementById('product-form');
    for (const field of ['product_name', 'brand', 'label', 'description', 'price', 'original_price',
      'image_url', 'composition_outer', 'composition_lining', 'washing_instructions', 'model_info']) {
      const el = form[field];
      if (el && p[field] != null) el.value = p[field];
    }

    currentSizes = (data.sizes || []).map(s => ({
      size_label: s.size_label,
      size_category: s.size_category || 'letter',
      stock_status: s.stock_status || 'unknown',
    }));
    renderSizes();
  } catch (e) {
    alert('Failed to load product: ' + e.message);
  }
}

async function saveProduct() {
  const form = document.getElementById('product-form');
  const statusEl = document.getElementById('save-status');

  const productName = form.product_name.value.trim();
  if (!productName) {
    statusEl.textContent = 'Product name is required';
    statusEl.style.color = '#f87171';
    return;
  }

  const data = {
    product_name: productName,
    brand: form.brand.value.trim(),
    label: form.label.value,
    description: form.description.value.trim(),
    price: parseFloat(form.price.value) || 0,
    original_price: parseFloat(form.original_price.value) || null,
    image_url: uploadedImageUrl || form.image_url.value.trim(),
    composition_outer: form.composition_outer.value.trim(),
    composition_lining: form.composition_lining.value.trim(),
    washing_instructions: form.washing_instructions.value.trim(),
    model_info: form.model_info.value.trim(),
    sizes: currentSizes.length > 0 ? currentSizes : null,
  };

  try {
    statusEl.textContent = 'Saving…';
    statusEl.style.color = '#fbbf24';

    let productId;
    if (editingProductId) {
      await updateProduct(editingProductId, data);
      productId = editingProductId;
    } else {
      const result = await createProduct(data);
      productId = result.product_id;
      editingProductId = productId;
      document.getElementById('edit-title').textContent = `Edit: ${productName}`;
    }

    // Update sizes if needed
    if (currentSizes.length > 0) {
      await updateSizes(productId, currentSizes);
    }

    statusEl.textContent = 'Saved!';
    statusEl.style.color = '#4ade80';
    setTimeout(() => { statusEl.textContent = ''; }, 3000);
  } catch (e) {
    statusEl.textContent = 'Error: ' + e.message;
    statusEl.style.color = '#f87171';
  }
}

// ---- Size Management ----
function addSizeRow() {
  currentSizes.push({ size_label: 'M', size_category: 'letter', stock_status: 'unknown' });
  renderSizes();
}

function removeSizeRow(index) {
  currentSizes.splice(index, 1);
  renderSizes();
}

function renderSizes() {
  const container = document.getElementById('sizes-container');
  if (!container) return;

  if (currentSizes.length === 0) {
    container.innerHTML = '<span style="font-size:12px;color:#666">No sizes configured</span>';
    return;
  }

  container.innerHTML = currentSizes.map((s, i) => `
    <div class="size-chip">
      <select data-size-label="${i}">
        ${SIZE_OPTIONS.map(o => `<option value="${o}" ${s.size_label === o ? 'selected' : ''}>${o}</option>`).join('')}
      </select>
      <select data-size-stock="${i}">
        ${STOCK_OPTIONS.map(o => `<option value="${o}" ${s.stock_status === o ? 'selected' : ''}>${o.replace(/_/g, ' ')}</option>`).join('')}
      </select>
      <button data-size-remove="${i}" title="Remove size">×</button>
    </div>
  `).join('');

  // Bind events
  container.querySelectorAll('[data-size-label]').forEach(el => {
    const i = parseInt(el.dataset.sizeLabel);
    el.addEventListener('change', () => { currentSizes[i].size_label = el.value; });
  });
  container.querySelectorAll('[data-size-stock]').forEach(el => {
    const i = parseInt(el.dataset.sizeStock);
    el.addEventListener('change', () => { currentSizes[i].stock_status = el.value; });
  });
  container.querySelectorAll('[data-size-remove]').forEach(el => {
    const i = parseInt(el.dataset.sizeRemove);
    el.addEventListener('click', () => removeSizeRow(i));
  });
}

// ---- Image Upload ----
async function handleImageUpload(e) {
  const file = e.target.files[0];
  if (!file) return;
  const preview = document.getElementById('upload-preview');
  preview.innerHTML = '<span style="font-size:12px;color:#fbbf24">Uploading…</span>';
  try {
    const result = await uploadImage(file);
    uploadedImageUrl = result.url;
    preview.innerHTML = `<img src="${result.url}" alt="Uploaded product image">`;
    // Also fill the image URL field
    const imgUrlInput = document.querySelector('input[name="image_url"]');
    if (imgUrlInput) imgUrlInput.value = result.url;
  } catch (err) {
    preview.innerHTML = `<span style="font-size:12px;color:#f87171">Upload failed: ${err.message}</span>`;
  }
}

init();
