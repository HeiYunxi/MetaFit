// ===== Fitting-room auth shim =====
// Single source of truth is /app/shared/auth.js. This module simply re-exports it
// so the 3D fitting room (which imports from './auth.js') shares ONE in-memory
// token/session with the 2D pages, and wires the 3D top-bar button to auth state.
//
// Previously this file duplicated the whole token-management logic, which caused
// the fitting room and the 2D pages to hold separate tokens (a source of bugs).
export {
  getAccessToken, getCurrentUser, isLoggedIn, isMerchant, authHeaders,
  setSession, clearSession, tryRefresh, fetchMe, register, login, logout,
  getThreadId, initAuth, onAuthChange,
} from '/app/shared/auth.js';

import { onAuthChange } from '/app/shared/auth.js';

// Reflect auth state on the 3D top-bar button (#auth-btn, created by ui-auth.js).
onAuthChange((user) => {
  const btn = document.getElementById('auth-btn');
  if (!btn) return;
  if (user) {
    btn.innerHTML = `\u{1F464} ${user.username}`;
    btn.title = `${user.role === 'merchant' ? '\u{1F3EA} Merchant' : '\u{1F464} User'} — click for menu`;
    btn.classList.add('logged-in');
  } else {
    btn.innerHTML = '\u{1F512} Login';
    btn.title = 'Login or Register';
    btn.classList.remove('logged-in');
  }
});
