// ===== Reusable login / register modal (injectable on any page) =====
import { login, register } from '/app/shared/auth.js';

let modal = null;

function build() {
  if (modal) return modal;
  modal = document.createElement('div');
  modal.id = 'auth-modal';
  modal.className = 'auth-modal-overlay';
  modal.innerHTML = `
    <div class="auth-modal-card">
      <div class="auth-tabs">
        <button id="tab-login" class="auth-tab active">Sign In</button>
        <button id="tab-register" class="auth-tab">Register</button>
      </div>
      <form id="login-form" class="auth-form">
        <input type="text" name="login" placeholder="Username or Email" required>
        <input type="password" name="password" placeholder="Password" required>
        <div id="login-error" class="auth-error"></div>
        <button type="submit" class="btn-primary auth-submit">Sign In</button>
      </form>
      <form id="register-form" class="auth-form" style="display:none">
        <input type="text" name="username" placeholder="Username (3-64 chars)" required>
        <input type="email" name="email" placeholder="Email" required>
        <input type="password" name="password" placeholder="Password (min 6 chars)" required>
        <select name="gender">
          <option value="prefer_not_to_say">Gender (optional)</option>
          <option value="female">Female</option>
          <option value="male">Male</option>
          <option value="other">Other</option>
        </select>
        <div id="register-error" class="auth-error"></div>
        <button type="submit" class="btn-primary auth-submit">Create Account</button>
      </form>
      <button id="auth-cancel" class="auth-cancel">Cancel</button>
    </div>`;
  document.body.appendChild(modal);

  const loginForm = modal.querySelector('#login-form');
  const registerForm = modal.querySelector('#register-form');
  const tabLogin = modal.querySelector('#tab-login');
  const tabReg = modal.querySelector('#tab-register');

  const switchTab = (which) => {
    const isLogin = which === 'login';
    tabLogin.classList.toggle('active', isLogin);
    tabReg.classList.toggle('active', !isLogin);
    loginForm.style.display = isLogin ? 'flex' : 'none';
    registerForm.style.display = isLogin ? 'none' : 'flex';
  };
  tabLogin.onclick = () => switchTab('login');
  tabReg.onclick = () => switchTab('register');

  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = modal.querySelector('#login-error');
    err.textContent = '';
    try {
      await login(e.target.login.value.trim(), e.target.password.value);
      close();
      e.target.reset();
      _resolve && _resolve(true);
    } catch (ex) { err.textContent = ex.message; }
  });

  registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = modal.querySelector('#register-error');
    err.textContent = '';
    const username = e.target.username.value.trim();
    const password = e.target.password.value;
    if (username.length < 3) { err.textContent = 'Username must be at least 3 characters'; return; }
    if (password.length < 6) { err.textContent = 'Password must be at least 6 characters'; return; }
    try {
      await register(username, e.target.email.value.trim(), password, e.target.gender.value);
      close();
      e.target.reset();
      _resolve && _resolve(true);
    } catch (ex) { err.textContent = ex.message; }
  });

  modal.querySelector('#auth-cancel').onclick = () => { close(); _resolve && _resolve(false); };
  modal.addEventListener('click', (e) => { if (e.target === modal) { close(); _resolve && _resolve(false); } });
  return modal;
}

let _resolve = null;

export function openAuthModal() {
  build();
  modal.classList.add('open');
  return new Promise((resolve) => { _resolve = resolve; });
}

export function close() {
  if (modal) modal.classList.remove('open');
}
