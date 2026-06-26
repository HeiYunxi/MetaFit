-- ===================================================================
-- MetaFit — complete MySQL schema (single source of truth)
--
-- Usage:
--   mysql -u root -p < sql/metafit.sql
--   python backend/scripts/apply_schema.py
--
-- All statements use CREATE TABLE IF NOT EXISTS (idempotent).
-- Target: MySQL 5.7+ / 8.0, utf8mb4_unicode_ci
-- ===================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE DATABASE IF NOT EXISTS metafit
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE metafit;

-- -------------------------------------------------------------------
-- 1. users
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    username            VARCHAR(64)      DEFAULT NULL COMMENT '用户名（注册用户）',
    password_hash       VARCHAR(255)     DEFAULT NULL COMMENT 'bcrypt hash（NULL=匿名未注册）',
    email               VARCHAR(128)     DEFAULT NULL,
    avatar_url          VARCHAR(512)     DEFAULT NULL,
    gender              ENUM('male','female','other','prefer_not_to_say') DEFAULT 'prefer_not_to_say',
    body_measurements   JSON             DEFAULT NULL COMMENT '{"height_cm":170,"weight_kg":60,"usual_size":"M"}',
    preferred_language  ENUM('zh','en','auto') DEFAULT 'auto' COMMENT 'RAG回复语言偏好',
    role                ENUM('user','merchant','admin') DEFAULT 'user',
    is_active           TINYINT(1)       DEFAULT 1,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_users_username (username),
    UNIQUE KEY idx_users_email (email),
    KEY idx_users_role (role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 2. sessions
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id                  CHAR(36)         NOT NULL COMMENT 'UUID，即 thread_id',
    user_id             BIGINT UNSIGNED  DEFAULT NULL COMMENT '登录后关联，匿名为NULL',
    client_ip           VARCHAR(45)      DEFAULT NULL,
    user_agent          VARCHAR(512)     DEFAULT NULL,
    is_active           TINYINT(1)       DEFAULT 1,
    last_activity_at    DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    expires_at          DATETIME         DEFAULT NULL COMMENT 'TTL过期时间',
    PRIMARY KEY (id),
    KEY idx_sessions_user (user_id),
    KEY idx_sessions_expires (expires_at),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 3. products
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    merchant_id         BIGINT UNSIGNED  DEFAULT NULL COMMENT 'NULL=系统Farfetch数据, 非NULL=商户上传',
    farfetch_id         VARCHAR(64)      DEFAULT NULL,
    brand_style_id      VARCHAR(64)      DEFAULT NULL,
    product_name        VARCHAR(512)     NOT NULL,
    brand               VARCHAR(256)     DEFAULT '',
    label               VARCHAR(128)     DEFAULT '' COMMENT '品类标签: New Season, Final Sale...',
    description         TEXT,
    price               DECIMAL(10,2)    DEFAULT 0.00,
    currency            CHAR(3)          DEFAULT 'CNY',
    original_price      DECIMAL(10,2)    DEFAULT NULL,
    discount_percentage DECIMAL(5,2)     DEFAULT NULL,
    image_url           VARCHAR(1024)    DEFAULT '',
    product_url         VARCHAR(1024)    DEFAULT '',
    composition_outer   VARCHAR(512)     DEFAULT '',
    composition_lining  VARCHAR(512)     DEFAULT '',
    washing_instructions TEXT,
    model_info          VARCHAR(512)     DEFAULT '',
    page_content        TEXT             NOT NULL COMMENT 'RAG检索预计算文本',
    image_available     TINYINT(1)       DEFAULT 0,
    image_checked_at    DATETIME         DEFAULT NULL,
    is_active           TINYINT(1)       DEFAULT 1 COMMENT '0=下架, 1=可检索',
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_prod_farfetch (farfetch_id),
    KEY idx_prod_merchant (merchant_id),
    KEY idx_prod_label (label),
    KEY idx_prod_brand (brand),
    KEY idx_prod_price (price),
    KEY idx_prod_active_label (is_active, label),
    FULLTEXT KEY idx_prod_ft (product_name, brand, description),
    CONSTRAINT fk_prod_merchant FOREIGN KEY (merchant_id) REFERENCES users(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 4. product_sizes
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_sizes (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    product_id          BIGINT UNSIGNED  NOT NULL,
    size_label          VARCHAR(32)      NOT NULL COMMENT 'XS,S,M,L,XL,One Size,34,36...',
    size_category       ENUM('letter','number','one_size','extended') NOT NULL,
    stock_status        ENUM('in_stock','low_stock','out_of_stock','unknown') DEFAULT 'unknown',
    PRIMARY KEY (id),
    UNIQUE KEY idx_prod_size (product_id, size_label),
    CONSTRAINT fk_size_product FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 5. coupons
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coupons (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    code                VARCHAR(64)      NOT NULL COMMENT '优惠券码',
    name                VARCHAR(128)     NOT NULL COMMENT '如"新人50元券"',
    discount_type       ENUM('fixed','percentage') NOT NULL,
    discount_value      DECIMAL(10,2)    NOT NULL,
    min_order_amount    DECIMAL(10,2)    DEFAULT 0.00,
    max_discount_amount DECIMAL(10,2)    DEFAULT NULL,
    usage_limit         INT UNSIGNED     DEFAULT 0 COMMENT '0=不限总发放量',
    per_user_limit      TINYINT UNSIGNED DEFAULT 1,
    valid_from          DATETIME         NOT NULL,
    valid_until         DATETIME         NOT NULL,
    is_active           TINYINT(1)       DEFAULT 1,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_coupon_code (code),
    KEY idx_coupon_active_date (is_active, valid_from, valid_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 6. conversations
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    session_id          CHAR(36)         NOT NULL,
    thread_id           CHAR(36)         NOT NULL COMMENT '冗余，同 sessions.id',
    graph_state         JSON             NOT NULL COMMENT 'RecState序列化',
    checkpoint_id       VARCHAR(128)     DEFAULT NULL,
    step                INT UNSIGNED     DEFAULT 0,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_conv_session (session_id),
    KEY idx_conv_latest (thread_id, step),
    CONSTRAINT fk_conv_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 7. messages
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    conversation_id     BIGINT UNSIGNED  NOT NULL,
    session_id          CHAR(36)         NOT NULL,
    role                ENUM('user','assistant','system') NOT NULL,
    content             TEXT             NOT NULL,
    metadata            JSON             DEFAULT NULL,
    created_at          DATETIME(3)      DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY idx_msg_session_ts (session_id, created_at),
    KEY fk_msg_conv (conversation_id),
    CONSTRAINT fk_msg_conv FOREIGN KEY (conversation_id) REFERENCES conversations(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_msg_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 8. cart_items
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cart_items (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    session_id          CHAR(36)         NOT NULL,
    product_id          BIGINT UNSIGNED  NOT NULL,
    selected_size       VARCHAR(32)      DEFAULT NULL,
    quantity            TINYINT UNSIGNED DEFAULT 1,
    added_at            DATETIME         DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_cart_unique (session_id, product_id),
    KEY fk_cart_product (product_id),
    CONSTRAINT fk_cart_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_cart_product FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 9. tryon_records
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tryon_records (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    session_id          CHAR(36)         NOT NULL,
    product_id          BIGINT UNSIGNED  DEFAULT NULL,
    person_image_hash   CHAR(64)         NOT NULL COMMENT 'SHA-256 of person image',
    product_image_url   VARCHAR(1024)    NOT NULL,
    result_image_base64 MEDIUMTEXT      DEFAULT NULL,
    result_image_url    VARCHAR(1024)    DEFAULT NULL,
    success             TINYINT(1)       NOT NULL,
    error_message       VARCHAR(512)     DEFAULT NULL,
    api_cost_usd        DECIMAL(8,4)     DEFAULT 0.0250,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tryon_dedup (person_image_hash, product_image_url(500), success, created_at),
    KEY idx_tryon_session (session_id),
    KEY fk_tryon_product (product_id),
    CONSTRAINT fk_tryon_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_tryon_product FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 10. img2model_tasks
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS img2model_tasks (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    session_id          CHAR(36)         NOT NULL,
    product_id          BIGINT UNSIGNED  DEFAULT NULL,
    tryon_record_id     BIGINT UNSIGNED  DEFAULT NULL,
    status              ENUM('pending','pose_normalize','mesh','rig','animation','done','failed') DEFAULT 'pending',
    progress            TINYINT UNSIGNED DEFAULT 0,
    pose_normalized     TINYINT(1)       DEFAULT 0,
    pose_task_id        VARCHAR(128)     DEFAULT NULL,
    mesh_task_id        VARCHAR(128)     DEFAULT NULL,
    mesh_glb_url        VARCHAR(1024)    DEFAULT NULL,
    rig_task_id         VARCHAR(128)     DEFAULT NULL,
    rig_glb_url         VARCHAR(1024)    DEFAULT NULL,
    rig_fbx_url         VARCHAR(1024)    DEFAULT NULL,
    anim_task_id        VARCHAR(128)     DEFAULT NULL,
    anim_glb_url        VARCHAR(1024)    DEFAULT NULL,
    anim_fbx_url        VARCHAR(1024)    DEFAULT NULL,
    animation_preset    VARCHAR(32)      DEFAULT NULL,
    error_message       VARCHAR(1024)    DEFAULT NULL,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_img2model_session (session_id),
    KEY idx_img2model_status (status, created_at),
    KEY fk_img2model_product (product_id),
    KEY fk_img2model_tryon (tryon_record_id),
    CONSTRAINT fk_img2model_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_img2model_product FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_img2model_tryon FOREIGN KEY (tryon_record_id) REFERENCES tryon_records(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 11. user_coupons
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_coupons (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id             BIGINT UNSIGNED  NOT NULL,
    coupon_id           BIGINT UNSIGNED  NOT NULL,
    session_id          CHAR(36)         DEFAULT NULL,
    status              ENUM('available','used','expired','revoked') DEFAULT 'available',
    used_at             DATETIME         DEFAULT NULL,
    used_order_id       BIGINT UNSIGNED  DEFAULT NULL,
    acquired_at         DATETIME         DEFAULT CURRENT_TIMESTAMP,
    expires_at          DATETIME         NOT NULL,
    PRIMARY KEY (id),
    KEY idx_uc_user_status (user_id, status),
    KEY idx_uc_session (session_id),
    KEY idx_uc_coupon (coupon_id),
    CONSTRAINT fk_uc_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_uc_coupon FOREIGN KEY (coupon_id) REFERENCES coupons(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_uc_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 12. user_coins
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_coins (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    user_id             BIGINT UNSIGNED  DEFAULT NULL,
    session_id          CHAR(36)         DEFAULT NULL,
    balance             INT UNSIGNED     DEFAULT 0,
    total_earned        INT UNSIGNED     DEFAULT 0,
    total_spent         INT UNSIGNED     DEFAULT 0,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_coins_user (user_id),
    UNIQUE KEY idx_coins_session (session_id),
    CONSTRAINT fk_coins_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_coins_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 13. coin_transactions
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coin_transactions (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    coin_account_id     BIGINT UNSIGNED  NOT NULL,
    amount              INT              NOT NULL COMMENT '正=收入, 负=支出',
    reason              VARCHAR(256)     NOT NULL,
    reference_type      VARCHAR(32)      DEFAULT NULL,
    reference_id        BIGINT UNSIGNED  DEFAULT NULL,
    balance_after       INT UNSIGNED     NOT NULL,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_ct_account (coin_account_id, created_at),
    CONSTRAINT fk_ct_account FOREIGN KEY (coin_account_id) REFERENCES user_coins(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 14. orders
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    order_no            VARCHAR(32)      NOT NULL,
    user_id             BIGINT UNSIGNED  DEFAULT NULL,
    session_id          CHAR(36)         DEFAULT NULL,
    used_coupon_id      BIGINT UNSIGNED  DEFAULT NULL,
    total_amount        DECIMAL(10,2)    NOT NULL,
    discount_amount     DECIMAL(10,2)    DEFAULT 0.00,
    final_amount        DECIMAL(10,2)    NOT NULL,
    status              ENUM('pending','paid','shipped','delivered','cancelled','refunded') DEFAULT 'pending',
    paid_at             DATETIME         DEFAULT NULL,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_order_no (order_no),
    KEY idx_order_user (user_id),
    KEY idx_order_session (session_id),
    KEY idx_order_status (status, created_at),
    KEY fk_order_uc (used_coupon_id),
    CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_order_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_order_uc FOREIGN KEY (used_coupon_id) REFERENCES user_coupons(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 15. order_items
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    order_id            BIGINT UNSIGNED  NOT NULL,
    product_id          BIGINT UNSIGNED  NOT NULL,
    product_name_snap   VARCHAR(512)     NOT NULL,
    price_snap          DECIMAL(10,2)    NOT NULL,
    selected_size       VARCHAR(32)      DEFAULT NULL,
    quantity            TINYINT UNSIGNED DEFAULT 1,
    PRIMARY KEY (id),
    KEY idx_oi_order (order_id),
    KEY idx_oi_product (product_id),
    CONSTRAINT fk_oi_order FOREIGN KEY (order_id) REFERENCES orders(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_oi_product FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE NO ACTION ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 16. browse_history
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS browse_history (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    session_id          CHAR(36)         NOT NULL,
    user_id             BIGINT UNSIGNED  DEFAULT NULL COMMENT '登录后回填',
    product_id          BIGINT UNSIGNED  NOT NULL,
    viewed_at           DATETIME         DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY idx_bh_unique (session_id, product_id),
    KEY idx_bh_user (user_id, viewed_at),
    KEY idx_bh_product (product_id),
    CONSTRAINT fk_bh_session FOREIGN KEY (session_id) REFERENCES sessions(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_bh_user FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_bh_product FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -------------------------------------------------------------------
-- 17. index_rebuild_log
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS index_rebuild_log (
    id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    triggered_by        BIGINT UNSIGNED  DEFAULT NULL,
    rebuild_type        ENUM('full','incremental','single') NOT NULL,
    product_id          BIGINT UNSIGNED  DEFAULT NULL,
    status              ENUM('running','done','failed') DEFAULT 'running',
    doc_count           INT UNSIGNED     DEFAULT 0,
    elapsed_ms          INT UNSIGNED     DEFAULT 0,
    error_message       VARCHAR(1024)    DEFAULT NULL,
    created_at          DATETIME         DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_irl_status (status, created_at),
    KEY fk_irl_user (triggered_by),
    KEY fk_irl_product (product_id),
    CONSTRAINT fk_irl_user FOREIGN KEY (triggered_by) REFERENCES users(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_irl_product FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
