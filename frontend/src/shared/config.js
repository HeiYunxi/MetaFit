// ===== Shared config (used by all pages, no three.js dependency) =====

export const API_URL =
  (window.location.protocol === 'http:' || window.location.protocol === 'https:')
    ? window.location.origin
    : 'http://localhost:8000';

// Ad / coins (also used by the 3D fitting room)
export const AD_VIDEO_URL = '/assets/ad.mp4';
export const AD_REWARD = 20;

// localStorage fallback keys (migration-period compatibility)
export const COINS_KEY = 'webxr_coins_v1';
export const COUPONS_KEY = 'webxr_coupons_v1';

// Local fallback coupon tiers (only used when the coins API is unavailable)
export const COUPON_TIERS = [
  { cost: 50,  label: '$5 off',  code: 'SAVE5' },
  { cost: 80,  label: '10% off', code: 'TENOFF' },
  { cost: 120, label: '$15 off', code: 'SAVE15' },
];

// Product category options shown in filters (label values match DB `products.label`)
export const CATEGORY_OPTIONS = [
  'New Season', 'Dress', 'Jacket', 'Coat', 'Shoes', 'Bag',
  'Top', 'Pants', 'Skirt', 'Accessories',
];
