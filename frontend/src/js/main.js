// ===== Main entry point — wires all modules together =====
import {
  initScene, enableVR, buildRedPacket, animateRedPacket, updateModelDisplay,
  renderer, camera, scene,
} from './scene.js';
import {
  setupFirstPersonControls, updateFirstPerson, updateDebugOverlay,
  finalizeSpawn, onEnterZone,
} from './player.js';
import {
  search, runZoneRecommend, runTryOn, generate3D,
  loadTrending, renderCart, toggleCart, toggleCoinPanel,
  openAd, closeAd, updateCoinBadge,
  hasSelectedProduct,
} from './ui.js';

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
document.getElementById('vr-toggle-btn').onclick = () => enableVR();
document.getElementById('cart-toggle-btn').onclick = toggleCart;
document.getElementById('coin-toggle-btn').onclick = toggleCoinPanel;
document.getElementById('ad-close-btn').onclick = closeAd;

// ---- Initial UI setup ----
setupFirstPersonControls();
renderCart();
loadTrending();
updateCoinBadge();
