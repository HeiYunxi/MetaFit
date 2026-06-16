// ===== First-person controls, collision detection, zone interaction =====
import * as THREE from 'three';
import {
  player, PLAYER_RADIUS, MAX_STEP_HEIGHT,
  WALKABLE, OBSTACLES, ZONES,
} from './config.js';
import { scene, camera, renderer, shopRoot, redPacket } from './scene.js';

// ---- Exported state ----
export let fpEnabled = false;
export let currentZone = null;
export let _floorY = 0;
export let debugMode = false;
export let debugGroup = null;
let lastFrameTime = 0;    // internal, used by animation loop

// ---- Internal state ----
const keys = Object.create(null);
const _forward = new THREE.Vector3();
const _right = new THREE.Vector3();
const _floorRay = new THREE.Raycaster();
const _down = new THREE.Vector3(0, -1, 0);
const _clickRay = new THREE.Raycaster();
const _clickPt = new THREE.Vector2();
let _zoneBannerTimer = null;
let _zoneHideTimer = null;

// ---- Height-based floor detection ----
// Returns the surface closest to refY (if given), otherwise the highest surface.
// Used for both collision checks and walking surface tracking.
export function getFloorHeight(x, z, refY) {
  _floorRay.set(new THREE.Vector3(x, 10, z), _down);
  let bestY = -Infinity;
  let bestDist = Infinity;
  if (shopRoot) {
    const hits = _floorRay.intersectObject(shopRoot, true);
    for (const h of hits) {
      if (refY !== undefined) {
        const d = Math.abs(h.point.y - refY);
        if (d < bestDist) { bestDist = d; bestY = h.point.y; }
      } else {
        if (h.point.y > bestY) bestY = h.point.y;
      }
    }
  }
  return isFinite(bestY) ? bestY : 0;
}

// Lowest surface (the actual ground — used only for initial spawn)
export function getGroundLevel(x, z) {
  _floorRay.set(new THREE.Vector3(x, 10, z), _down);
  let lowestY = Infinity;
  if (shopRoot) {
    const hits = _floorRay.intersectObject(shopRoot, true);
    for (const h of hits) {
      if (h.point.y < lowestY) lowestY = h.point.y;
    }
  }
  return isFinite(lowestY) ? lowestY : 0;
}

// ---- Collision test ----
export function canStand(x, z) {
  if (WALKABLE.minX === undefined) return true; // boundary not calibrated yet
  const r = PLAYER_RADIUS;
  if (x - r < WALKABLE.minX || x + r > WALKABLE.maxX ||
      z - r < WALKABLE.minZ || z + r > WALKABLE.maxZ) return false;
  for (const o of OBSTACLES) {
    if (x + r > o.minX && x - r < o.maxX &&
        z + r > o.minZ && z - r < o.maxZ) return false;
  }
  // Height check: don't walk onto surfaces too far from current floor level
  if (shopRoot) {
    const floorH = getFloorHeight(x, z, _floorY);
    if (Math.abs(floorH - _floorY) > MAX_STEP_HEIGHT) return false;
  }
  return true;
}

// ---- Setup mouse + keyboard controls ----
export function setupFirstPersonControls() {
  const el = renderer.domElement;
  let dragging = false, lastX = 0, lastY = 0, moved = 0;

  el.addEventListener('mousedown', (e) => {
    dragging = true; lastX = e.clientX; lastY = e.clientY; moved = 0;
  });
  window.addEventListener('mouseup', (e) => {
    dragging = false;
    if (moved < 6) handleSceneClick(e.clientX, e.clientY);
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX, dy = e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    moved += Math.abs(dx) + Math.abs(dy);
    player.yaw   -= dx * 0.0025;
    player.pitch -= dy * 0.0025;
    const lim = Math.PI / 2 - 0.05;
    player.pitch = Math.max(-lim, Math.min(lim, player.pitch));
  });

  const isTyping = () => document.activeElement &&
    ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName);
  window.addEventListener('keydown', (e) => {
    if (isTyping()) return;
    keys[e.code] = true;
    if (e.code === 'KeyG') toggleDebug();
  });
  window.addEventListener('keyup', (e) => { keys[e.code] = false; });
}

// ---- Scene click (red packet detection) ----
function handleSceneClick(clientX, clientY) {
  if (!redPacket) return;
  const rect = renderer.domElement.getBoundingClientRect();
  _clickPt.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  _clickPt.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  _clickRay.setFromCamera(_clickPt, camera);
  const hits = _clickRay.intersectObject(redPacket, true);
  if (hits.length && window._openAd) window._openAd();
}

// ---- Per-frame update ----
export function updateFirstPerson(dt) {
  // Apply look direction
  camera.position.copy(player.pos);
  const cy = Math.cos(player.yaw), sy = Math.sin(player.yaw);
  const cp = Math.cos(player.pitch), sp = Math.sin(player.pitch);
  const lookDir = new THREE.Vector3(-sy * cp, sp, -cy * cp);
  camera.lookAt(player.pos.x + lookDir.x, player.pos.y + lookDir.y, player.pos.z + lookDir.z);

  if (!fpEnabled || !dt) return;

  _forward.set(-sy, 0, -cy);
  _right.set(cy, 0, -sy);
  let mx = 0, mz = 0;
  if (keys['KeyW'] || keys['ArrowUp'])    { mx += _forward.x; mz += _forward.z; }
  if (keys['KeyS'] || keys['ArrowDown'])  { mx -= _forward.x; mz -= _forward.z; }
  if (keys['KeyD'] || keys['ArrowRight']) { mx += _right.x;   mz += _right.z; }
  if (keys['KeyA'] || keys['ArrowLeft'])  { mx -= _right.x;   mz -= _right.z; }
  if (mx === 0 && mz === 0) return;

  const len = Math.hypot(mx, mz);
  mx = mx / len * player.speed * dt;
  mz = mz / len * player.speed * dt;

  // Per-axis collision (height-aware: reject moves that would jump onto tables)
  const nx = player.pos.x + mx;
  const nz = player.pos.z + mz;
  let movedFloorY = _floorY;
  if (canStand(nx, player.pos.z)) {
    const fy = shopRoot ? getFloorHeight(nx, player.pos.z, movedFloorY) : _floorY;
    if (Math.abs(fy - movedFloorY) <= MAX_STEP_HEIGHT) {
      player.pos.x = nx;
      movedFloorY = fy;
    }
  }
  if (canStand(player.pos.x, nz)) {
    const fy = shopRoot ? getFloorHeight(player.pos.x, nz, movedFloorY) : _floorY;
    if (Math.abs(fy - movedFloorY) <= MAX_STEP_HEIGHT) {
      player.pos.z = nz;
      movedFloorY = fy;
    }
  }
  _floorY = movedFloorY;
  player.pos.y = player.eyeY + _floorY;

  checkZone();
}

// ---- Zone detection ----
export function pointInRect(x, z, r) {
  return x >= r.minX && x <= r.maxX && z >= r.minZ && z <= r.maxZ;
}

export function checkZone() {
  const p = player.pos;
  const zone = ZONES.find((z) => pointInRect(p.x, p.z, z.rect)) || null;
  if (zone === currentZone) return;
  currentZone = zone;
  hideZoneBanner();
  if (zone && window._onEnterZone) window._onEnterZone(zone);
}

// ---- Zone banner ----
export function showZoneBanner(text, actionLabel, onAction) {
  const el = document.getElementById('zone-banner');
  if (!el) return;
  if (_zoneBannerTimer) { clearTimeout(_zoneBannerTimer); _zoneBannerTimer = null; }
  if (_zoneHideTimer) { clearTimeout(_zoneHideTimer); _zoneHideTimer = null; }
  el.innerHTML = '';
  const span = document.createElement('span');
  span.textContent = text;
  el.appendChild(span);
  el.style.display = 'flex';
  el.style.alignItems = 'center';
  el.style.gap = '12px';
  el.style.opacity = '1';

  if (actionLabel && onAction) {
    const btn = document.createElement('button');
    btn.textContent = actionLabel;
    btn.style.cssText = 'padding:6px 14px;border:none;border-radius:16px;background:#fff;color:#4338ca;font-size:13px;font-weight:600;cursor:pointer';
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      hideZoneBanner();
      onAction();
    });
    el.appendChild(btn);
  }
}

export function hideZoneBanner() {
  const el = document.getElementById('zone-banner');
  if (!el) return;
  el.style.opacity = '0';
  if (_zoneHideTimer) clearTimeout(_zoneHideTimer);
  _zoneHideTimer = setTimeout(() => { el.style.display = 'none'; _zoneHideTimer = null; }, 300);
}

// ---- Zone enter handler (called from main.js via _onEnterZone bridge) ----
export function onEnterZone(zone, callbacks) {
  if (zone.action === 'recommend') {
    showZoneBanner('📍 ' + zone.name, 'Browse →', () => callbacks.runZoneRecommend(zone.query));
  } else if (zone.action === 'highlight') {
    if (zone.message) showZoneBanner('📍 ' + zone.name + ' — ' + zone.message);
  } else if (zone.action === 'tryon') {
    const panel = document.getElementById('tryon-panel');
    if (panel) panel.classList.remove('hidden');
    if (!callbacks.hasSelectedProduct()) {
      showZoneBanner('📍 Fitting Room — pick an item first, then upload your photo');
    }
  } else if (zone.action === 'model3d') {
    const panel = document.getElementById('model-panel');
    if (panel) panel.classList.remove('hidden');
    if (zone.message) showZoneBanner('📍 ' + zone.name + ' — ' + zone.message);
  }
}

// ---- Debug overlay ----
export function toggleDebug() {
  debugMode = !debugMode;
  const el = document.getElementById('debug-overlay');
  if (el) el.style.display = debugMode ? 'block' : 'none';
  if (debugGroup) debugGroup.visible = debugMode;
  if (debugMode) rebuildDebugRects();
}

function rebuildDebugRects() {
  if (debugGroup) { scene.remove(debugGroup); debugGroup.traverse(o => o.geometry && o.geometry.dispose()); }
  debugGroup = new THREE.Group();
  const addRect = (r, color, y) => {
    if (!r) return;
    const pts = [
      new THREE.Vector3(r.minX, y, r.minZ), new THREE.Vector3(r.maxX, y, r.minZ),
      new THREE.Vector3(r.maxX, y, r.maxZ), new THREE.Vector3(r.minX, y, r.maxZ),
      new THREE.Vector3(r.minX, y, r.minZ),
    ];
    const g = new THREE.BufferGeometry().setFromPoints(pts);
    debugGroup.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color })));
  };
  addRect(WALKABLE, 0x38bdf8, 0.02);
  OBSTACLES.forEach(o => addRect(o, 0xf87171, 0.04));
  ZONES.forEach(z => addRect(z.rect, 0x4ade80, 0.06));
  debugGroup.visible = debugMode;
  scene.add(debugGroup);
}

export function updateDebugOverlay() {
  if (!debugMode) return;
  const el = document.getElementById('debug-overlay');
  if (!el) return;
  const p = player.pos;
  const deg = (player.yaw * 180 / Math.PI).toFixed(0);
  el.textContent =
    `x: ${p.x.toFixed(2)}  z: ${p.z.toFixed(2)}  (eyeY ${p.y.toFixed(2)})\n` +
    `yaw: ${deg}°  floorY: ${_floorY.toFixed(3)}  stepMax: ${MAX_STEP_HEIGHT.toFixed(2)}\n` +
    (WALKABLE.minX !== undefined ? `walkable: x[${WALKABLE.minX.toFixed(1)}, ${WALKABLE.maxX.toFixed(1)}]  z[${WALKABLE.minZ.toFixed(1)}, ${WALKABLE.maxZ.toFixed(1)}]\n` : '') +
    `obstacles: ${OBSTACLES.length}  ·  press G to hide`;
}

// ---- Finalize spawn after shop loads ----
export function finalizeSpawn(finalSize) {
  // Use ground level (lowest surface) for spawn, not highest (could be a table)
  player.eyeY = Math.min(0.48, finalSize.y * 0.5);
  player.pos.set(0.09, player.eyeY, 1.57);
  player.yaw = 61 * Math.PI / 180;
  player.pitch = 0;
  _floorY = getGroundLevel(player.pos.x, player.pos.z);
  player.pos.y = player.eyeY + _floorY;
  camera.near = 0.05;
  camera.far = Math.max(finalSize.x, finalSize.z) * 6;
  camera.updateProjectionMatrix();
  fpEnabled = true;
  rebuildDebugRects();
}
