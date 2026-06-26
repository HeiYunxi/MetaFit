// ===== Auth UI: Login / Register modal =====
import { login, register, logout, isLoggedIn, getCurrentUser, isMerchant, tryRefresh } from './auth.js';

// ---- Create auth modal (injected to DOM on init) ----
export function initAuthUI() {
  // Create auth button in the top bar
  const rightSide = document.getElementById('right-side');
  if (!rightSide) return;

  // 返回主页按钮
  const homeBtn = document.createElement('button');
  homeBtn.id = 'home-btn';
  homeBtn.style.cssText = `
    position:absolute; top:20px; right:450px; padding:10px 16px;
    border-radius:8px; border:1px solid #444;
    background:rgba(42,42,74,0.9); color:#cbd5e1; font-size:13px;
    cursor:pointer; z-index:20;
  `;
  homeBtn.innerHTML = '\u{1F3E0} Home';
  homeBtn.addEventListener('click', () => { window.location.href = '/MetaClothesShop'; });
  rightSide.appendChild(homeBtn);

  // 个人主页 / 登录入口（合并为单一按钮）：
  // - 未登录显示 "🔒 Login" → 弹出登录框
  // - 已登录显示 "👤 用户名" → 弹出用户菜单（含 My Profile 跳转个人主页）
  const btn = document.createElement('button');
  btn.id = 'auth-btn';
  btn.style.cssText = `
    position:absolute; top:20px; right:340px; padding:10px 16px;
    border-radius:8px; border:1px solid #444;
    background:rgba(42,42,74,0.9); color:#a78bfa; font-size:13px;
    cursor:pointer; z-index:20;
  `;
  btn.innerHTML = '\u{1F512} Login';
  rightSide.appendChild(btn);

  // Click: if logged in, show user menu; else show auth modal
  btn.addEventListener('click', () => {
    if (isLoggedIn()) {
      toggleUserMenu();
    } else {
      showAuthModal();
    }
  });

  // Create user menu dropdown
  createUserMenu(rightSide);

  // Create auth modal
  createAuthModal(rightSide);

  // Try auto-refresh on page load
  tryRefresh();
}

// ---- User Menu Dropdown ----
let userMenu = null;

function createUserMenu(parent) {
  userMenu = document.createElement('div');
  userMenu.id = 'user-menu';
  userMenu.className = 'hidden';
  userMenu.style.cssText = `
    position:absolute; top:56px; right:340px; z-index:50;
    background:#1e1e3a; border:1px solid #444; border-radius:10px;
    padding:8px 0; min-width:200px; box-shadow:0 8px 24px rgba(0,0,0,0.5);
  `;
  userMenu.innerHTML = `
    <div class="menu-item" data-action="profile" style="padding:10px 16px;cursor:pointer;color:#cbd5e1;font-size:13px">
      \u{1F4CB} My Profile
    </div>
    <div class="menu-item" data-action="orders" style="padding:10px 16px;cursor:pointer;color:#cbd5e1;font-size:13px">
      \u{1F4E6} My Orders
    </div>
    <div class="menu-item" data-action="history" style="padding:10px 16px;cursor:pointer;color:#cbd5e1;font-size:13px">
      \u{1F4AC} Chat History
    </div>
    <div class="menu-item" data-action="coupons" style="padding:10px 16px;cursor:pointer;color:#cbd5e1;font-size:13px">
      \u{1F3F7}️ My Coupons
    </div>
    <div id="merchant-link" class="menu-item" data-action="merchant" style="padding:10px 16px;cursor:pointer;color:#fbbf24;font-size:13px;display:none">
      \u{1F3EA} Merchant Portal
    </div>
    <div style="border-top:1px solid #333;margin:4px 0"></div>
    <div class="menu-item" data-action="logout" style="padding:10px 16px;cursor:pointer;color:#f87171;font-size:13px">
      \u{1F6AA} Logout
    </div>
  `;
  parent.appendChild(userMenu);

  // Menu item clicks
  userMenu.querySelectorAll('.menu-item').forEach(item => {
    item.addEventListener('click', async (e) => {
      e.stopPropagation();
      const action = item.dataset.action;
      if (action === 'logout') {
        await logout();
        hideUserMenu();
      } else if (action === 'merchant') {
        window.open('/merchant', '_blank');
        hideUserMenu();
      } else if (action === 'profile' || action === 'orders' || action === 'history') {
        // 个人信息/订单/历史都迁移到独立的个人主页
        window.location.href = '/profile';
      } else if (action === 'coupons') {
        if (window.toggleCoinPanel) {
          window.toggleCoinPanel();
          hideUserMenu();
        }
      }
    });
  });

  // Close menu when clicking outside
  document.addEventListener('click', (e) => {
    if (userMenu && !userMenu.classList.contains('hidden')) {
      if (!userMenu.contains(e.target) && e.target.id !== 'auth-btn') {
        hideUserMenu();
      }
    }
  });
}

function toggleUserMenu() {
  if (!userMenu) return;
  const show = userMenu.classList.contains('hidden');
  if (show) {
    // Show merchant link if applicable
    const ml = document.getElementById('merchant-link');
    if (ml) ml.style.display = isMerchant() ? 'block' : 'none';
  }
  userMenu.classList.toggle('hidden');
}

function hideUserMenu() {
  if (userMenu) userMenu.classList.add('hidden');
}

// ---- Auth Modal ----
let authModal = null;

function createAuthModal(parent) {
  authModal = document.createElement('div');
  authModal.id = 'auth-modal';
  authModal.className = 'hidden';
  authModal.style.cssText = `
    position:absolute; inset:0; z-index:70;
    background:rgba(0,0,0,0.85); display:none;
    align-items:center; justify-content:center;
  `;

  authModal.innerHTML = `
    <div style="background:#1e1e3a; border:1px solid #555; border-radius:14px;
                padding:28px 24px; width:380px; max-height:90vh; overflow-y:auto;
                box-shadow:0 12px 40px rgba(0,0,0,0.6)">
      <div style="display:flex; margin-bottom:20px; border-bottom:2px solid #333">
        <button id="tab-login" class="auth-tab active"
                style="flex:1;padding:10px;background:none;border:none;color:#a78bfa;
                       font-size:15px;font-weight:600;cursor:pointer;border-bottom:2px solid #a78bfa;margin-bottom:-2px">
          Sign In
        </button>
        <button id="tab-register" class="auth-tab"
                style="flex:1;padding:10px;background:none;border:none;color:#666;
                       font-size:15px;font-weight:600;cursor:pointer">
          Register
        </button>
      </div>

      <!-- Login form -->
      <form id="login-form" style="display:flex;flex-direction:column;gap:12px">
        <input type="text" name="login" placeholder="Username or Email" required
               style="padding:10px;border-radius:8px;border:1px solid #444;background:#12122a;color:#fff;font-size:14px">
        <input type="password" name="password" placeholder="Password" required
               style="padding:10px;border-radius:8px;border:1px solid #444;background:#12122a;color:#fff;font-size:14px">
        <div id="login-error" style="color:#f87171;font-size:12px;display:none"></div>
        <button type="submit"
                style="padding:10px;border-radius:8px;border:none;background:#7c3aed;color:#fff;
                       font-size:14px;font-weight:600;cursor:pointer;margin-top:4px">
          Sign In
        </button>
      </form>

      <!-- Register form -->
      <form id="register-form" style="display:none;flex-direction:column;gap:10px">
        <input type="text" name="username" placeholder="Username (3-64 chars)" required
               style="padding:10px;border-radius:8px;border:1px solid #444;background:#12122a;color:#fff;font-size:14px">
        <input type="email" name="email" placeholder="Email" required
               style="padding:10px;border-radius:8px;border:1px solid #444;background:#12122a;color:#fff;font-size:14px">
        <input type="password" name="password" placeholder="Password (min 6 chars)" required
               style="padding:10px;border-radius:8px;border:1px solid #444;background:#12122a;color:#fff;font-size:14px">
        <select name="gender"
                style="padding:10px;border-radius:8px;border:1px solid #444;background:#12122a;color:#fff;font-size:14px">
          <option value="prefer_not_to_say">Gender (optional)</option>
          <option value="female">Female</option>
          <option value="male">Male</option>
          <option value="other">Other</option>
        </select>
        <div id="register-error" style="color:#f87171;font-size:12px;display:none"></div>
        <button type="submit"
                style="padding:10px;border-radius:8px;border:none;background:#7c3aed;color:#fff;
                       font-size:14px;font-weight:600;cursor:pointer;margin-top:4px">
          Create Account
        </button>
      </form>

      <button id="close-auth-modal"
              style="width:100%;margin-top:12px;padding:8px;border-radius:8px;
                     border:1px solid #444;background:transparent;color:#888;font-size:12px;cursor:pointer">
        Cancel
      </button>
    </div>
  `;
  parent.appendChild(authModal);

  // Tab switching
  authModal.querySelector('#tab-login').addEventListener('click', () => switchAuthTab('login'));
  authModal.querySelector('#tab-register').addEventListener('click', () => switchAuthTab('register'));

  // Form submissions
  authModal.querySelector('#login-form').addEventListener('submit', handleLogin);
  authModal.querySelector('#register-form').addEventListener('submit', handleRegister);

  // Close
  authModal.querySelector('#close-auth-modal').addEventListener('click', hideAuthModal);
  authModal.addEventListener('click', (e) => {
    if (e.target === authModal) hideAuthModal();
  });
}

export function showAuthModal() {
  if (!authModal) return;
  authModal.classList.remove('hidden');
  authModal.style.display = 'flex';
}

function hideAuthModal() {
  if (!authModal) return;
  authModal.classList.add('hidden');
  authModal.style.display = 'none';
}

function switchAuthTab(tab) {
  const loginTab = document.getElementById('tab-login');
  const registerTab = document.getElementById('tab-register');
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');

  if (tab === 'login') {
    loginTab.style.color = '#a78bfa';
    loginTab.style.borderBottom = '2px solid #a78bfa';
    registerTab.style.color = '#666';
    registerTab.style.borderBottom = 'none';
    loginForm.style.display = 'flex';
    registerForm.style.display = 'none';
  } else {
    registerTab.style.color = '#a78bfa';
    registerTab.style.borderBottom = '2px solid #a78bfa';
    loginTab.style.color = '#666';
    loginTab.style.borderBottom = 'none';
    registerForm.style.display = 'flex';
    loginForm.style.display = 'none';
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const loginVal = e.target.login.value.trim();
  const password = e.target.password.value;
  const errEl = document.getElementById('login-error');

  if (!loginVal || !password) {
    errEl.textContent = 'Please fill in all fields';
    errEl.style.display = 'block';
    return;
  }

  try {
    await login(loginVal, password);
    hideAuthModal();
    e.target.reset();
    errEl.style.display = 'none';
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = 'block';
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const username = e.target.username.value.trim();
  const email = e.target.email.value.trim();
  const password = e.target.password.value;
  const gender = e.target.gender.value;
  const errEl = document.getElementById('register-error');

  if (username.length < 3) {
    errEl.textContent = 'Username must be at least 3 characters';
    errEl.style.display = 'block';
    return;
  }
  if (password.length < 6) {
    errEl.textContent = 'Password must be at least 6 characters';
    errEl.style.display = 'block';
    return;
  }

  try {
    await register(username, email, password, gender);
    hideAuthModal();
    e.target.reset();
    errEl.style.display = 'none';
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = 'block';
  }
}

// ---- Profile Panel ----
function showProfilePanel() {
  const user = getCurrentUser();
  if (!user) return;
  const panel = document.getElementById('tryon-panel');
  if (!panel) return;

  const measurements = user.body_measurements || {};
  panel.classList.remove('hidden');
  panel.innerHTML = `
    <h3>\u{1F464} My Profile</h3>
    <div style="font-size:13px;color:#cbd5e1;line-height:1.8">
      <p><b>Username:</b> ${user.username}</p>
      <p><b>Email:</b> ${user.email || '—'}</p>
      <p><b>Role:</b> ${user.role === 'merchant' ? '\u{1F3EA} Merchant' : user.role === 'admin' ? '\u{1F6E1}️ Admin' : '\u{1F464} User'}</p>
      <p><b>Gender:</b> ${user.gender || '—'}</p>
      <p style="margin-top:8px"><b>\u{1F4CF} Body Measurements:</b></p>
      <ul style="font-size:12px;margin-top:4px">
        <li>Height: ${measurements.height_cm || '—'} cm</li>
        <li>Weight: ${measurements.weight_kg || '—'} kg</li>
        <li>Usual Size: ${measurements.usual_size || '—'}</li>
        <li>Shoulder: ${measurements.shoulder_width_cm || '—'} cm</li>
        <li>Chest: ${measurements.chest_cm || '—'} cm</li>
        <li>Waist: ${measurements.waist_cm || '—'} cm</li>
        <li>Hip: ${measurements.hip_cm || '—'} cm</li>
      </ul>
    </div>
    <button id="close-profile-btn" style="margin-top:12px;padding:6px 16px;border-radius:6px;
      border:1px solid #555;background:rgba(60,60,80,0.9);color:#fff;font-size:12px;cursor:pointer">
      Close
    </button>
  `;

  panel.querySelector('#close-profile-btn').addEventListener('click', () => {
    panel.classList.add('hidden');
  });
}

// Export for global
window.showAuthModal = showAuthModal;
