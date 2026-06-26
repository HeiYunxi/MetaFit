// ===== Main entry point — wires all modules together =====
import { API_URL } from './config.js';
import {
  initScene, buildRedPacket, animateRedPacket, updateModelDisplay,
  loadModel, renderer, camera, scene,
} from './scene.js';
import {
  setupFirstPersonControls, updateFirstPerson, updateDebugOverlay,
  finalizeSpawn, onEnterZone,
} from './player.js';
import {
  search, runZoneRecommend, runTryOn, generate3D,
  loadTrending, renderCart, toggleCart, toggleCoinPanel,
  openAd, closeAd, updateCoinBadge,
  hasSelectedProduct, selectProduct, replayMessages,
} from './ui.js';
import { getSessionMessages } from './api.js';
import { initAuthUI } from './ui-auth.js';

// ---- Bridge: global callbacks for cross-module communication ----
window._openAd = openAd;
window._onEnterZone = (zone) => {
  onEnterZone(zone, { runZoneRecommend, hasSelectedProduct });
};

// ---- Animation loop ----
let lastFrameTime = 0;

// ---- Init scene (pass callbacks for when shop finishes loading) ----
initScene({
  onLoaded(shop, meshes, finalSize) {
    finalizeSpawn(finalSize);
  },
  onBuildRedPacket() {
    buildRedPacket();
  },
});

// Start the render loop
renderer.setAnimationLoop((time) => {
  const dt = lastFrameTime ? Math.min((time - lastFrameTime) / 1000, 0.1) : 0;
  lastFrameTime = time;
  updateFirstPerson(dt);
  animateRedPacket(time / 1000);
  updateModelDisplay(dt);
  updateDebugOverlay();
  renderer.render(scene, camera);
});

// ---- Bind UI events ----
document.getElementById('search-btn').onclick = () => {
  const q = document.getElementById('query-input').value.trim();
  if (q) search(q);
};
const queryInput = document.getElementById('query-input');
queryInput.addEventListener('keydown', (e) => {
  e.stopPropagation();
  if (e.key === 'Enter') { e.preventDefault(); search(queryInput.value.trim()); }
});
queryInput.addEventListener('keyup', (e) => e.stopPropagation());
queryInput.addEventListener('keypress', (e) => e.stopPropagation());
document.getElementById('tryon-btn').onclick = runTryOn;
document.getElementById('gen3d-btn').onclick = generate3D;
document.getElementById('cart-toggle-btn').onclick = toggleCart;
document.getElementById('coin-toggle-btn').onclick = toggleCoinPanel;
document.getElementById('ad-close-btn').onclick = closeAd;

// ---- Initial UI setup ----
setupFirstPersonControls();
initAuthUI();
renderCart();
loadTrending();
updateCoinBadge();

// Deep-link handling for ?product / ?model / ?session.
(async () => {
  const params = new URLSearchParams(window.location.search);
  const pid = params.get('product');
  const modelUrl = params.get('model');
  const session = params.get('session');

  // From a product page: preselect product for try-on.
  if (pid) {
    try {
      const r = await fetch('/products/' + pid);
      if (r.ok) {
        const { product } = await r.json();
        if (product) {
          selectProduct(product);
          const status = document.getElementById('model-status');
          if (status) status.textContent = `Selected: ${product.product_name}. Upload a photo to try on.`;
        }
      }
    } catch {}
  }

  // From generation history: load the saved 3D model directly.
  if (modelUrl) {
    const abs = /^(https?:)?\/\//i.test(modelUrl)
      ? modelUrl
      : (API_URL || '').replace(/\/$/, '') + (modelUrl.startsWith('/') ? modelUrl : '/' + modelUrl);
    try {
      loadModel(abs);
      document.getElementById('model-panel')?.classList.remove('hidden');
      const status = document.getElementById('model-status');
      if (status) status.textContent = 'Loaded model from your generation history. Walk into the 3D Showcase zone to view.';
    } catch {}
  }

  // From generation history: replay the related conversation.
  if (session) {
    try {
      const { items } = await getSessionMessages(session);
      replayMessages(items);
    } catch {}
  }
})();
