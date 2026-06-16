import * as THREE from 'three';

// ===== API & Asset URLs =====
export const API_URL = (window.location.protocol === 'http:' || window.location.protocol === 'https:')
  ? window.location.origin
  : 'http://localhost:8000';

export const SHOP_GLB_URL = '/assets/ClothesShop_optimized.glb';
export const SHOP_TARGET_SIZE = 12;
export const SHOP_FALLBACK_BG = '/assets/background.png';
export const AD_VIDEO_URL = '/assets/ad.mp4';
export const SKYBOX_IMAGE_URL = '/assets/sky.jpg';   // 设为 null 则使用程序化渐变天空

// ===== Player settings =====
export const player = {
  pos: new THREE.Vector3(0, 0.9, 0),
  yaw: 0,
  pitch: 0,
  speed: 1.584,
  eyeY: 0.4,
};

// ===== Collision & navigation =====
export const PLAYER_RADIUS = 0.2;
export const MAX_STEP_HEIGHT = 0.25;
// Boundary set after shop loads (mutable object — scene.js fills in the values)
export const WALKABLE = { minX: undefined, maxX: undefined, minZ: undefined, maxZ: undefined };
// Fitting Room (non-walkable), split to avoid Lounge extension area
export const OBSTACLES = [
  { minX: 1.6, maxX: 1.95, minZ: 0.5, maxZ: 0.7 },   // below Lounge ext
  { minX: 1.95, maxX: 2.54, minZ: 0.5, maxZ: 1.2 },  // right of Lounge ext
];

// ===== Interaction zones (floor-plane rectangles in metres) =====
export const ZONES = [
  { name: 'Womenswear', rect: { minX: -1.2, maxX: -0.6, minZ: 0.5, maxZ: 2.16 },
    action: 'recommend', query: "women's clothing" },
  { name: 'Menswear', rect: { minX: -0.6, maxX: 0.35, minZ: 1.2, maxZ: 2.16 },
    action: 'recommend', query: "men's clothing" },
  { name: 'Kidswear', rect: { minX: -0.6, maxX: 0.35, minZ: 0.5, maxZ: 1.2 },
    action: 'recommend', query: "children's clothing" },
  { name: 'Lounge', rect: { minX: 0.35, maxX: 1.95, minZ: 0.5, maxZ: 2.16 },
    action: 'highlight', message: 'Take a seat and browse 👜' },
  { name: 'Fitting Room', rect: { minX: 1.6, maxX: 2.54, minZ: 0.5, maxZ: 1.2 },
    action: 'tryon' },
  { name: '3D Showcase', rect: { minX: 1.6, maxX: 2.54, minZ: 1.2, maxZ: 2.16 },
    action: 'model3d', message: '3D Model Display — your generated model appears here' },
];

// ===== 3D model display position =====
export const MODEL_DISPLAY_POS = new THREE.Vector3(2.07, 0, 1.68);
/** Fixed showcase model height (metres). */
export const MODEL_TARGET_HEIGHT = 0.58;
/** Extra local Y lift so feet sit on the rug instead of clipping through. */
export const MODEL_FEET_LIFT = 0.18;
/** Cap used for room-height ratio (legacy / fallback). */
export const MODEL_MAX_ROOM_HEIGHT = 2.6;
/** Showcase model auto-rotation speed (rad/s); 2π/15 ≈ one full turn every 15s. */
export const MODEL_ROTATE_SPEED = (2 * Math.PI) / 15;

// ===== Red packet position =====
export const RED_PACKET_POS = new THREE.Vector3(0.89, 0, 1.09);

// ===== Coins & coupons =====
export const COINS_KEY = 'webxr_coins_v1';
export const COUPONS_KEY = 'webxr_coupons_v1';
export const AD_REWARD = 20;

export const COUPON_TIERS = [
  { cost: 50,  label: '$5 off',    code: 'SAVE5' },
  { cost: 80,  label: '10% off',   code: 'TENOFF' },
  { cost: 120, label: '$15 off',   code: 'SAVE15' },
];

// ===== Saved décor keys =====
export const DECOR_KEY = 'webxr_textured_v2';
export const DECOR_OLD_KEY = 'webxr_reupholstered_v1';
export const DELETED_KEY = 'webxr_deleted_v1';
