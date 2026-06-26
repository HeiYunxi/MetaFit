// ===== 3D Scene, Rendering, Shop Environment, Model Display =====
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import {
  SHOP_GLB_URL, SHOP_TARGET_SIZE, SHOP_FALLBACK_BG, API_URL, SKYBOX_IMAGE_URL,
  MODEL_DISPLAY_POS, RED_PACKET_POS,
  DECOR_KEY, DECOR_OLD_KEY, DELETED_KEY, WALKABLE,
  MODEL_TARGET_HEIGHT, MODEL_FEET_LIFT, MODEL_MAX_ROOM_HEIGHT, MODEL_ROTATE_SPEED,
  player,
} from './config.js';

// ---- Draco loader ----
const dracoLoader = new DRACOLoader();
dracoLoader.setDecoderPath('https://unpkg.com/three@0.160.0/examples/jsm/libs/draco/');
export function createGLTFLoader() {
  const loader = new GLTFLoader();
  loader.setDRACOLoader(dracoLoader);
  return loader;
}

// ---- Core Three.js objects (exported so other modules can use them) ----
export let scene, camera, renderer, modelGroup, envGroup;
export let shopRoot = null;
export let redPacket = null;
/** Shop interior height (metres), set when the shop GLB finishes loading. */
export let shopRoomHeight = 3.5;

const _floorRay = new THREE.Raycaster();
const _down = new THREE.Vector3(0, -1, 0);

/** Walkable surface at (x, z) — pick hit closest to expected floor, not the lowest geometry. */
function getFloorYAt(x, z, refY = 0.45) {
  if (!shopRoot) return refY;
  _floorRay.set(new THREE.Vector3(x, 10, z), _down);
  const hits = _floorRay.intersectObject(shopRoot, true);
  let bestY = refY;
  let bestDist = Infinity;
  for (const h of hits) {
    if (h.point.y > refY + 1.2) continue;
    const d = Math.abs(h.point.y - refY);
    if (d < bestDist) {
      bestDist = d;
      bestY = h.point.y;
    }
  }
  return bestY;
}

// ---- Animation playback + showcase rotation ----
let modelMixer = null;
let modelDisplayPivot = null;

/** Advance embedded GLB animation + slow 360° showcase rotation. */
export function updateModelDisplay(dt) {
  if (modelMixer) modelMixer.update(dt);
  if (modelDisplayPivot) {
    modelDisplayPivot.rotation.y += MODEL_ROTATE_SPEED * dt;
  }
}

// ---- Deleted meshes (persisted) ----
export function loadDeletedSet() {
  try { return new Set(JSON.parse(localStorage.getItem(DELETED_KEY) || '[]')); }
  catch { return new Set(); }
}

// ---- Procedural textures ----
function makeFabricTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const ctx = c.getContext('2d');
  const g = ctx.createLinearGradient(0, 0, 512, 512);
  g.addColorStop(0, '#33495a');
  g.addColorStop(1, '#22323f');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 512, 512);
  ctx.strokeStyle = 'rgba(200,180,140,0.35)';
  ctx.lineWidth = 2;
  const step = 64;
  ctx.save();
  ctx.translate(256, 256);
  ctx.rotate(Math.PI / 4);
  for (let i = -512; i <= 512; i += step) {
    ctx.beginPath(); ctx.moveTo(i, -512); ctx.lineTo(i, 512); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-512, i); ctx.lineTo(512, i); ctx.stroke();
  }
  ctx.restore();
  ctx.fillStyle = 'rgba(214,196,160,0.5)';
  for (let x = 0; x <= 512; x += step) {
    for (let y = 0; y <= 512; y += step) {
      ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill();
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(3, 3);
  return tex;
}

let _fabricTex = null;
export function getFabricTexture() {
  if (!_fabricTex) _fabricTex = makeFabricTexture();
  return _fabricTex;
}

export function makeFloorTileTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 512;
  const ctx = c.getContext('2d');
  const tile = 256, grout = 10;
  ctx.fillStyle = '#3a3d42';
  ctx.fillRect(0, 0, 512, 512);
  const tones = ['#b9bcc1', '#c4c7cc', '#aeb2b8', '#bfc2c7'];
  let t = 0;
  for (let y = 0; y < 512; y += tile) {
    for (let x = 0; x < 512; x += tile) {
      const fx = x + grout / 2, fy = y + grout / 2, fs = tile - grout;
      ctx.fillStyle = tones[t++ % tones.length];
      ctx.fillRect(fx, fy, fs, fs);
      ctx.save();
      ctx.beginPath(); ctx.rect(fx, fy, fs, fs); ctx.clip();
      ctx.strokeStyle = 'rgba(90,95,105,0.45)';
      ctx.lineWidth = 2;
      for (let v = 0; v < 4; v++) {
        const sx = fx + Math.random() * fs, sy = fy + Math.random() * fs;
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.bezierCurveTo(sx + 40 - Math.random() * 80, sy + 30,
          sx - 30 + Math.random() * 70, sy + 90, sx + 20 - Math.random() * 60, fy + fs);
        ctx.stroke();
      }
      ctx.strokeStyle = 'rgba(245,245,250,0.4)';
      ctx.lineWidth = 1;
      for (let v = 0; v < 3; v++) {
        const sx = fx + Math.random() * fs;
        ctx.beginPath();
        ctx.moveTo(sx, fy);
        ctx.bezierCurveTo(sx + 30, fy + 60, sx - 40, fy + 140, sx + 10, fy + fs);
        ctx.stroke();
      }
      ctx.restore();
      ctx.strokeStyle = 'rgba(255,255,255,0.4)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(fx, fy + fs); ctx.lineTo(fx, fy); ctx.lineTo(fx + fs, fy);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(0,0,0,0.25)';
      ctx.beginPath();
      ctx.moveTo(fx + fs, fy); ctx.lineTo(fx + fs, fy + fs); ctx.lineTo(fx, fy + fs);
      ctx.stroke();
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  return tex;
}

let _floorTex = null;
export function getFloorTileTexture() {
  if (!_floorTex) _floorTex = makeFloorTileTexture();
  return _floorTex;
}

// ---- Saved décor ----
export function loadSavedDecor() {
  try {
    const raw = JSON.parse(localStorage.getItem(DECOR_KEY) || '{}');
    const old = JSON.parse(localStorage.getItem(DECOR_OLD_KEY) || '[]');
    old.forEach((n) => { if (!(n in raw)) raw[n] = 'fabric'; });
    return raw;
  } catch { return {}; }
}

export function applySavedTexture(mesh, kind) {
  const tex = kind === 'wood' ? getFloorTileTexture() : getFabricTexture();
  const apply = (m) => {
    if (!m) return new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8 });
    const nm = m.clone();
    nm.map = tex;
    if (nm.color) nm.color.setHex(0xffffff);
    if ('roughness' in nm) nm.roughness = kind === 'wood' ? 0.75 : 0.8;
    if ('metalness' in nm) nm.metalness = 0.0;
    nm.needsUpdate = true;
    return nm;
  };
  mesh.material = Array.isArray(mesh.material) ? mesh.material.map(apply) : apply(mesh.material);
}

// ---- Scene initialisation ----
// callbacks: { onShopLoaded(shop, meshes, finalSize), onBuildRedPacket() }
export function initScene(callbacks = {}) {
  scene = new THREE.Scene();

  camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  camera.position.set(0, 1.6, 3);

  // Lighting
  const mainLight = new THREE.DirectionalLight(0xffffff, 1.0);
  mainLight.position.set(3, 5, 5);
  mainLight.castShadow = true;
  mainLight.shadow.mapSize.width = 1024;
  mainLight.shadow.mapSize.height = 1024;
  mainLight.shadow.camera.near = 0.5;
  mainLight.shadow.camera.far = 50;
  mainLight.shadow.camera.left = -10;
  mainLight.shadow.camera.right = 10;
  mainLight.shadow.camera.top = 10;
  mainLight.shadow.camera.bottom = -10;
  mainLight.shadow.bias = -0.0005;
  mainLight.shadow.normalBias = 0.02;
  scene.add(mainLight);
  const fillLight = new THREE.DirectionalLight(0xffffff, 1.4);
  fillLight.position.set(-2, 3, -3);
  scene.add(fillLight);
  const topLight = new THREE.DirectionalLight(0xffffff, 1.2);
  topLight.position.set(0, 8, 0);
  scene.add(topLight);
  scene.add(new THREE.AmbientLight(0xffffff, 1.5));
  scene.add(new THREE.HemisphereLight(0xffffff, 0x888888, 0.9));

  // Sky dome — image-based if SKYBOX_IMAGE_URL is set, otherwise procedural gradient
  const skyGeo = new THREE.SphereGeometry(30, 64, 32);
  const buildProceduralSky = () => {
    return new THREE.ShaderMaterial({
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {},
      vertexShader: /* glsl */ `
        varying vec3 vWorldPos;
        void main() {
          vec4 worldPos = modelMatrix * vec4(position, 1.0);
          vWorldPos = worldPos.xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        varying vec3 vWorldPos;
        void main() {
          float h = normalize(vWorldPos).y;
          float t = smoothstep(-0.05, 0.35, h);
          vec3 skyTop   = vec3(0.38, 0.58, 0.85);
          vec3 horizon  = vec3(0.75, 0.84, 0.95);
          vec3 col = mix(horizon, skyTop, t);
          gl_FragColor = vec4(col, 1.0);
        }
      `,
    });
  };
  let skyMat;
  if (SKYBOX_IMAGE_URL) {
    skyMat = new THREE.MeshBasicMaterial({ side: THREE.BackSide, depthWrite: false });
    new THREE.TextureLoader().load(
      SKYBOX_IMAGE_URL,
      (tex) => { skyMat.map = tex; skyMat.needsUpdate = true; },
      undefined,
      () => { skyMat.dispose(); skyDome.material = buildProceduralSky(); }
    );
  } else {
    skyMat = buildProceduralSky();
  }
  const skyDome = new THREE.Mesh(skyGeo, skyMat);
  skyDome.name = 'skyDome';
  scene.add(skyDome);

  modelGroup = new THREE.Group();
  scene.add(modelGroup);

  envGroup = new THREE.Group();
  scene.add(envGroup);

  const container = document.getElementById('right-side');
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setClearColor(0x1a1a2e, 1);
  updateRendererSize();
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  // ── Tone mapping (Unity-like ACES filmic) ──
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.25;
  // ── Shadow map ──
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.style.pointerEvents = 'auto';
  container.insertBefore(renderer.domElement, container.firstChild);

  // Generate IBL environment map from sky dome (gives PBR reflections, must be after renderer)
  const pmremGenerator = new THREE.PMREMGenerator(renderer);
  pmremGenerator.compileEquirectangularShader();
  const envScene = new THREE.Scene();
  envScene.add(skyDome.clone());
  const envMap = pmremGenerator.fromScene(envScene, 0.04).texture;
  scene.environment = envMap;
  pmremGenerator.dispose();

  scene.background = new THREE.Color(0x1a1a2e);
  loadShopEnvironment(callbacks);

  window.addEventListener('resize', () => updateRendererSize());
}

export function updateRendererSize() {
  const container = document.getElementById('right-side');
  const w = container.clientWidth;
  const h = container.clientHeight;
  if (w && h) {
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
}

// ---- Load shop environment GLB ----
export function loadShopEnvironment(callbacks = {}) {
  const statusEl = document.getElementById('shop-status');
  const setStatus = (msg, err) => {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.style.color = err ? '#f87171' : '#4ade80';
  };
  const loader = createGLTFLoader();
  loader.load(
    SHOP_GLB_URL,
    (gltf) => {
      const shop = gltf.scene;
      shop.updateWorldMatrix(true, true);

      // Robust bounding box (ignore outlier meshes)
      const meshes = [];
      shop.traverse((o) => { if (o.isMesh && o.geometry) meshes.push(o); });

      const centers = [];
      meshes.forEach((m) => {
        if (!m.geometry.boundingBox) m.geometry.computeBoundingBox();
        const c = m.geometry.boundingBox.getCenter(new THREE.Vector3());
        c.applyMatrix4(m.matrixWorld);
        centers.push(c);
        m.userData._wc = c;
      });

      const median = (arr) => {
        const s = [...arr].sort((a, b) => a - b);
        return s[Math.floor(s.length / 2)] || 0;
      };
      const med = new THREE.Vector3(
        median(centers.map((c) => c.x)),
        median(centers.map((c) => c.y)),
        median(centers.map((c) => c.z))
      );
      const dists = centers.map((c) => c.distanceTo(med)).sort((a, b) => a - b);
      const medDist = dists[Math.floor(dists.length / 2)] || 1;
      const cutoff = Math.max(medDist * 8, 1);

      const robustBox = new THREE.Box3();
      let kept = 0, dropped = 0;
      meshes.forEach((m) => {
        if (m.userData._wc.distanceTo(med) <= cutoff) {
          m.geometry.computeBoundingBox();
          const b = m.geometry.boundingBox.clone().applyMatrix4(m.matrixWorld);
          robustBox.union(b);
          kept++;
        } else {
          m.visible = false;
          dropped++;
        }
      });

      // Scale to target size
      const size = robustBox.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z) || 1;
      shop.scale.setScalar(SHOP_TARGET_SIZE / maxDim);
      shop.updateWorldMatrix(true, true);

      // Centre on floor
      const finalBox = new THREE.Box3();
      meshes.forEach((m) => {
        if (!m.visible) return;
        m.geometry.computeBoundingBox();
        finalBox.union(m.geometry.boundingBox.clone().applyMatrix4(m.matrixWorld));
      });
      const center = finalBox.getCenter(new THREE.Vector3());
      shop.position.x -= center.x;
      shop.position.z -= center.z;
      shop.position.y -= finalBox.min.y;
      envGroup.add(shop);

      // Fix materials: untextured → warm beige
      let meshCount = 0, texturedMat = 0, repairedMat = 0;
      const matSet = new Set();
      const WALL_BEIGE = 0xe6dcc8;
      const CEIL_CREAM = 0xf0ebe0;
      const ACCENTS = [0xd8c9ad, 0xcdbb9a, 0xe0d4bd, 0xc4b291];
      let accentIdx = 0;
      const floorY = 0;

      shop.traverse((o) => {
        if (!(o.isMesh && o.visible)) return;
        meshCount++;

        o.geometry.computeBoundingBox();
        const wb = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld);
        const ws = wb.getSize(new THREE.Vector3());
        const isFlat = ws.y < Math.min(ws.x, ws.z) * 0.25;
        const isLarge = ws.x * ws.z > 1.0;
        const nearFloor = wb.min.y <= floorY + 0.3;
        const isCeiling = isFlat && isLarge && !nearFloor;

        if (!o.material) {
          o.material = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.0 });
        }

        const mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach((m) => {
          if (!m) return;
          if (m.map) {
            texturedMat++;
            if (matSet.has(m.uuid)) return;
            matSet.add(m.uuid);
            m.map.colorSpace = THREE.SRGBColorSpace;
            m.map.needsUpdate = true;
            if (m.color) m.color.setHex(0xffffff);
            if ('roughness' in m) m.roughness = Math.min(m.roughness ?? 1, 0.9);
            if ('metalness' in m) m.metalness = Math.min(m.metalness ?? 0, 0.1);
            m.needsUpdate = true;
            return;
          }
          if (matSet.has(m.uuid)) return;
          matSet.add(m.uuid);

          let tone;
          if (isCeiling) tone = CEIL_CREAM;
          else {
            const hex = m.color ? m.color.getHex() : 0xffffff;
            if (hex === 0xffffff || hex === 0xcccccc) {
              tone = (m.color && m.color.getHex() === 0xffffff)
                ? WALL_BEIGE
                : ACCENTS[accentIdx++ % ACCENTS.length];
            } else {
              tone = null;
            }
          }
          if (tone !== null && m.color) { m.color.setHex(tone); repairedMat++; }

          if ('roughness' in m) m.roughness = Math.max(m.roughness ?? 0, 0.7);
          if ('metalness' in m) m.metalness = Math.min(m.metalness ?? 0, 0.1);
          if (m.opacity < 0.1) m.opacity = 1.0;
          m.transparent = m.opacity < 1.0;
        });
      });

      // Enable shadows on shop meshes (large ones cast, all receive)
      shop.traverse((o) => {
        if (!(o.isMesh && o.visible)) return;
        o.castShadow = true;
        o.receiveShadow = true;
      });

      // Apply saved décor
      const decor = loadSavedDecor();
      if (Object.keys(decor).length) {
        shop.traverse((o) => {
          if (o.isMesh && o.visible && decor[o.name]) applySavedTexture(o, decor[o.name]);
        });
      }

      // Hide deleted objects
      shopRoot = shop;
      // Calibrated room footprint (metres)
      Object.assign(WALKABLE, { minX: -1.2, maxX: 2.54, minZ: 0.5, maxZ: 2.16 });

      const deleted = loadDeletedSet();
      if (deleted.size) {
        shop.traverse((o) => {
          if (o.isMesh && deleted.has(o.name)) o.visible = false;
        });
      }

      // Final bounds
      shop.updateWorldMatrix(true, true);
      const fb = new THREE.Box3();
      meshes.forEach((m) => {
        if (!m.visible) return;
        m.geometry.computeBoundingBox();
        fb.union(m.geometry.boundingBox.clone().applyMatrix4(m.matrixWorld));
      });
      const finalSize = fb.getSize(new THREE.Vector3());
      // Shop bbox Y often includes ceiling structure; cap for human-scale display math.
      shopRoomHeight = Math.min(finalSize.y, MODEL_MAX_ROOM_HEIGHT);
      console.log('[SHOP] kept', kept, 'meshes, dropped', dropped, 'outliers',
        '| final bounds(m):', finalSize.x.toFixed(2), finalSize.y.toFixed(2), finalSize.z.toFixed(2),
        '| textured:', texturedMat, 'repaired:', repairedMat);

      // Remove background colour
      scene.background = null;
      setStatus(`Shop loaded · ${kept} meshes (dropped ${dropped} outliers) · ${texturedMat} textured / ${repairedMat} repaired · bounds ${finalSize.x.toFixed(1)}×${finalSize.y.toFixed(1)}×${finalSize.z.toFixed(1)}m`);
      setTimeout(() => { if (statusEl) statusEl.style.display = 'none'; }, 8000);

      // Fire callback so other modules can finalize setup
      if (callbacks.onLoaded) callbacks.onLoaded(shop, meshes, finalSize);
      if (callbacks.onBuildRedPacket) callbacks.onBuildRedPacket();
    },
    (xhr) => {
      if (xhr.total) {
        const pct = Math.round((xhr.loaded / xhr.total) * 100);
        setStatus(`Downloading shop model… ${pct}% (${(xhr.loaded/1048576).toFixed(0)}/${(xhr.total/1048576).toFixed(0)} MB)`);
      } else {
        setStatus(`Downloading shop model… ${(xhr.loaded/1048576).toFixed(0)} MB`);
      }
    },
    (err) => {
      console.warn('Shop GLB not loaded, falling back to background image.', err);
      setStatus('Shop model failed to load — using fallback background. See console.', true);
      const bgLoader = new THREE.TextureLoader();
      bgLoader.load(API_URL + SHOP_FALLBACK_BG, (texture) => {
        scene.background = texture;
      }, undefined, () => {
        scene.background = new THREE.Color(0x1a1a2e);
      });
    }
  );
}

// ---- Load a GLB into the model display group ----
export function loadModel(url) {
  while (modelGroup.children.length) modelGroup.remove(modelGroup.children[0]);
  modelMixer = null;
  modelDisplayPivot = null;
  const loader = createGLTFLoader();
  loader.load(url,
    (gltf) => {
      const model = gltf.scene;
      model.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(model);
      const size = box.getSize(new THREE.Vector3());

      const floorY = getFloorYAt(MODEL_DISPLAY_POS.x, MODEL_DISPLAY_POS.z, player.eyeY || 0.48);
      const targetHeight = MODEL_TARGET_HEIGHT;

      // Prefer Y as standing axis; fall back if bbox is degenerate.
      let rawHeight = size.y;
      if (rawHeight < 0.05 || rawHeight < size.x * 0.25) {
        rawHeight = Math.max(size.y, size.z, 0.001);
      }
      let scale = targetHeight / rawHeight;
      scale = Math.min(Math.max(scale, 0.01), 3);

      model.scale.setScalar(scale);
      model.updateMatrixWorld(true);
      box.setFromObject(model);
      size.copy(box.getSize(new THREE.Vector3()));

      const center = box.getCenter(new THREE.Vector3());
      modelDisplayPivot = new THREE.Group();
      modelDisplayPivot.position.set(MODEL_DISPLAY_POS.x, floorY, MODEL_DISPLAY_POS.z);
      // Local space: feet on pivot floor + lift, centered on XZ → Y-axis spin.
      model.position.set(-center.x, -box.min.y + MODEL_FEET_LIFT, -center.z);
      modelDisplayPivot.add(model);
      modelGroup.add(modelDisplayPivot);

      console.log(
        `[MODEL] scale=${scale.toFixed(4)} targetH=${targetHeight.toFixed(2)}m `
        + `feetLift=${MODEL_FEET_LIFT.toFixed(2)}m floorY=${floorY.toFixed(3)} `
        + `bbox=${size.x.toFixed(2)}×${size.y.toFixed(2)}×${size.z.toFixed(2)}`,
      );

      // If the GLB ships with baked animation (rig+anim pipeline), loop every clip.
      if (gltf.animations && gltf.animations.length) {
        modelMixer = new THREE.AnimationMixer(model);
        gltf.animations.forEach((clip) => {
          const action = modelMixer.clipAction(clip);
          action.setLoop(THREE.LoopRepeat, Infinity);
          action.clampWhenFinished = false;
          action.play();
        });
        console.log('[MODEL] playing', gltf.animations.length, 'embedded animation clip(s)');
      } else {
        console.log('[MODEL] no embedded animation in GLB (static model loaded)');
      }

      renderer.domElement.style.pointerEvents = 'auto';
    },
    undefined,
    (e) => console.error('GLB load error:', e)
  );
}

// ---- Red packet 3D object ----
export function buildRedPacket() {
  const g = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.12, 0.17, 0.02),
    new THREE.MeshStandardMaterial({ color: 0xd11d2a, roughness: 0.5, metalness: 0.1 })
  );
  g.add(body);
  const seal = new THREE.Mesh(
    new THREE.CircleGeometry(0.035, 24),
    new THREE.MeshStandardMaterial({ color: 0xf5c518, roughness: 0.4, metalness: 0.5 })
  );
  seal.position.set(0, 0.02, 0.011);
  g.add(seal);
  g.userData.isRedPacket = true;
  body.userData.isRedPacket = true;
  seal.userData.isRedPacket = true;
  g.position.copy(RED_PACKET_POS);
  g.position.y = 1.0;
  g.rotation.x = -0.35;
  redPacket = g;
  scene.add(g);
}

export function animateRedPacket(t) {
  if (!redPacket) return;
  redPacket.rotation.y = Math.sin(t * 1.5) * 0.4;
  redPacket.position.y = 1.0 + Math.sin(t * 2) * 0.015;
}
