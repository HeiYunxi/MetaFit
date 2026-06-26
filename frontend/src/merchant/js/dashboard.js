// ===== Dashboard Page =====
import { fetchProfile, rebuildIndex, getRebuildStatus, getMerchantUser, logout } from './merchant-api.js';

async function init() {
  // Check login
  const user = getMerchantUser();
  if (!user) {
    showLogin();
    return;
  }
  document.getElementById('merchant-name').textContent = user.username || 'Merchant';

  // Bind logout
  document.getElementById('logout-btn').addEventListener('click', () => logout());

  // Load profile stats
  try {
    const profile = await fetchProfile();
    document.getElementById('stat-products').textContent = profile.product_count || 0;
    document.getElementById('stat-orders').textContent = profile.total_orders || 0;
  } catch (e) {
    console.warn('Failed to load profile:', e);
  }

  // Check last rebuild
  try {
    const status = await getRebuildStatus();
    const last = status.last_rebuild;
    if (last) {
      document.getElementById('rebuild-status').textContent =
        `Last index rebuild: ${new Date(last.created_at).toLocaleString()} — ${last.doc_count || 0} docs, ${(last.elapsed_ms/1000).toFixed(1)}s`;
    }
  } catch {}

  // Bind buttons
  document.getElementById('new-product-btn')?.addEventListener('click', () => {
    navigate('product-edit');
  });
  document.getElementById('add-product-btn')?.addEventListener('click', () => {
    navigate('product-edit');
  });

  // Rebuild button
  const rebuildBtn = document.getElementById('rebuild-btn');
  const rebuildBtn2 = document.getElementById('rebuild-btn2');

  function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

  async function pollRebuild(logId) {
    const statusEl = document.getElementById('rebuild-status');
    for (let i = 0; i < 180; i++) {
      await sleep(2000);
      const { last_rebuild: last } = await getRebuildStatus();
      if (!last || last.id !== logId) continue;
      if (last.status === 'running') {
        statusEl.textContent = 'Rebuilding indexes in background…';
        continue;
      }
      if (last.status === 'done') {
        statusEl.textContent =
          `Rebuild done: ${last.doc_count || 0} docs in ${((last.elapsed_ms || 0) / 1000).toFixed(1)}s`;
        return;
      }
      if (last.status === 'failed') {
        statusEl.textContent = `Rebuild failed: ${last.error_message || 'unknown error'}`;
        return;
      }
    }
    statusEl.textContent = 'Rebuild still running — check status later.';
  }

  async function doRebuild() {
    const statusEl = document.getElementById('rebuild-status');
    statusEl.textContent = 'Starting rebuild…';
    try {
      const result = await rebuildIndex();
      if (result.status === 'running' && result.log_id) {
        statusEl.textContent = 'Rebuilding indexes in background…';
        await pollRebuild(result.log_id);
      } else if (result.doc_count != null) {
        statusEl.textContent =
          `Rebuild done: ${result.doc_count} docs in ${((result.elapsed_ms || 0) / 1000).toFixed(1)}s`;
      } else {
        statusEl.textContent = result.message || 'Rebuild started';
      }
    } catch (e) {
      statusEl.textContent = `Rebuild failed: ${e.message}`;
    }
  }
  rebuildBtn?.addEventListener('click', (e) => { e.preventDefault(); doRebuild(); });
  rebuildBtn2?.addEventListener('click', doRebuild);

  // Navigation
  setupNavigation();
}

function showLogin() {
  const inputStyle = "padding:10px;border-radius:8px;border:1px solid #444;background:#12122a;color:#fff;font-size:14px";
  document.getElementById('content').innerHTML = `
    <div style="max-width:380px;margin:80px auto;background:#1e1e3a;border-radius:14px;padding:28px 24px;border:1px solid #2a2a4a">
      <h1 id="auth-title" style="text-align:center;margin-bottom:20px">\u{1F3EA} Merchant Login</h1>

      <form id="merchant-login-form" style="display:flex;flex-direction:column;gap:12px">
        <input type="text" id="login-input" placeholder="Username or Email" required style="${inputStyle}">
        <input type="password" id="password-input" placeholder="Password" required style="${inputStyle}">
        <div id="login-error" style="color:#f87171;font-size:12px;display:none"></div>
        <button type="submit" class="btn-primary" style="width:100%">Sign In</button>
      </form>

      <form id="merchant-register-form" style="display:none;flex-direction:column;gap:12px">
        <input type="text" id="reg-username" placeholder="Username (3-64 chars)" required style="${inputStyle}">
        <input type="email" id="reg-email" placeholder="Email" required style="${inputStyle}">
        <input type="password" id="reg-password" placeholder="Password (min 6 chars)" required style="${inputStyle}">
        <div id="register-error" style="color:#f87171;font-size:12px;display:none"></div>
        <button type="submit" class="btn-primary" style="width:100%">Create Merchant Account</button>
      </form>

      <p style="margin-top:12px;font-size:12px;color:#888;text-align:center">
        <span id="auth-switch-text">Need a merchant account?</span>
        <a href="#" id="auth-switch" style="color:#a78bfa">Register here</a>
      </p>
    </div>
  `;

  const loginForm = document.getElementById('merchant-login-form');
  const registerForm = document.getElementById('merchant-register-form');
  const title = document.getElementById('auth-title');
  const switchText = document.getElementById('auth-switch-text');
  const switchLink = document.getElementById('auth-switch');

  switchLink.addEventListener('click', (e) => {
    e.preventDefault();
    const showReg = registerForm.style.display === 'none';
    registerForm.style.display = showReg ? 'flex' : 'none';
    loginForm.style.display = showReg ? 'none' : 'flex';
    title.textContent = showReg ? '\u{1F3EA} Merchant Register' : '\u{1F3EA} Merchant Login';
    switchText.textContent = showReg ? 'Already have an account?' : 'Need a merchant account?';
    switchLink.textContent = showReg ? 'Sign in' : 'Register here';
  });

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('login-error');
    errEl.style.display = 'none';
    try {
      const { merchantLogin } = await import('./merchant-api.js');
      await merchantLogin(
        document.getElementById('login-input').value,
        document.getElementById('password-input').value,
      );
      window.location.reload();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    }
  });

  registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('register-error');
    errEl.style.display = 'none';
    try {
      const { merchantRegister } = await import('./merchant-api.js');
      await merchantRegister(
        document.getElementById('reg-username').value.trim(),
        document.getElementById('reg-email').value.trim(),
        document.getElementById('reg-password').value,
      );
      window.location.reload();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    }
  });
}

// ---- Navigation ----
function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const page = link.dataset.page;
      if (page) navigate(page);
    });
  });
}

function navigate(page) {
  // Update nav
  document.querySelectorAll('.nav-item[data-page]').forEach(l => l.classList.remove('active'));
  const activeLink = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (activeLink) activeLink.classList.add('active');

  // Update content
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const target = document.getElementById(`page-${page}`);
  if (target) {
    target.classList.add('active');
    // Trigger page-specific init
    if (page === 'products') window._initProductList?.();
    if (page === 'orders') window._initOrders?.();
  }
}

// Make navigate global
window._navigate = navigate;

init();
