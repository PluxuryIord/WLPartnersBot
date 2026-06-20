-- Migration 001: wl_admon_* tables for the parquet-from-S3 loader.
--
-- Apply once on FDM_WinlinePartners (the bot's main MySQL).
-- After applying, start `wl_admon_loader.service`. The loader will
-- backfill all wl_admon_* tables from s3://wldp-admon-export/.
--
-- Idempotent: all CREATE TABLE statements use IF NOT EXISTS.

-- ── 1. Users (snapshot, ~14k rows, refreshed daily) ─────────────────────────
CREATE TABLE IF NOT EXISTS wl_admon_users (
  id              BIGINT       NOT NULL PRIMARY KEY,
  email           VARCHAR(255),
  role            VARCHAR(64),
  status          TINYINT,
  email_confirmed TINYINT(1),
  first_name      VARCHAR(255),
  last_name       VARCHAR(255),
  middle_name     VARCHAR(255),
  phone           VARCHAR(64),
  telegram        VARCHAR(128),
  created_ms      VARCHAR(32),
  last_login_ms   VARCHAR(32),
  credit          VARCHAR(64),
  debit           VARCHAR(64),
  manager_email   VARCHAR(255),
  referrer_email  VARCHAR(255),
  KEY idx_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 2. Websites (snapshot, ~8k rows, refreshed daily) ───────────────────────
CREATE TABLE IF NOT EXISTS wl_admon_websites (
  id             BIGINT       NOT NULL PRIMARY KEY,
  alias          VARCHAR(64),
  name           VARCHAR(255),
  type           INT,
  status         TINYINT,
  user_id        BIGINT,
  user_email     VARCHAR(255),
  manager_email  VARCHAR(255),
  url            VARCHAR(512),
  created_ms     VARCHAR(32),
  KEY idx_websites_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 3. Offers (snapshot, ~15 rows, daily) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS wl_admon_offers (
  id      VARCHAR(64)  NOT NULL PRIMARY KEY,
  alias   VARCHAR(64),
  name    VARCHAR(255),
  status  TINYINT,
  KEY idx_offers_alias (alias)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 4. Conversions (incremental, hourly, UPSERT by id) ──────────────────────
CREATE TABLE IF NOT EXISTS wl_admon_conversions (
  id             VARCHAR(64)   NOT NULL PRIMARY KEY,
  date           DATE,
  goal           VARCHAR(32),
  status         TINYINT,
  reward         BIGINT,
  partner_email  VARCHAR(255),
  created_ms     VARCHAR(32),
  updated_ms     VARCHAR(32),
  KEY idx_conv_partner_date (partner_email, date),
  KEY idx_conv_date (date),
  KEY idx_conv_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 5. stats_group_by (daily snapshot, UPSERT by composite hash) ────────────
--
-- The natural composite key (datetz, user_id, website_id, offer_id, offer_tag,
-- link) exceeds InnoDB's 3072-byte index limit on utf8mb4, so we hash it.
-- dedupe_hash = SHA1 of '|'-joined composite, computed in the loader.
CREATE TABLE IF NOT EXISTS wl_admon_stats_group_by (
  dedupe_hash       CHAR(40)     NOT NULL PRIMARY KEY,
  datetz            DATE,
  user_id           BIGINT,
  website_id        BIGINT,
  offer_id          VARCHAR(128),
  offer_tag         VARCHAR(512),
  link              TEXT,
  -- metrics
  clicks            INT,
  goal11_quantity   INT,
  goal12_quantity   INT,
  goal13_quantity   INT,
  reward_confirmed  BIGINT,
  reward_created    DOUBLE,
  reward_canceled   BIGINT,
  reward_processing DOUBLE,
  KEY idx_sgb_user_date (user_id, datetz),
  KEY idx_sgb_date (datetz)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── 6. Service table: which S3 keys have already been ingested ──────────────
CREATE TABLE IF NOT EXISTS wl_admon_ingested (
  table_name   VARCHAR(64)   NOT NULL,
  s3_key       VARCHAR(512)  NOT NULL,
  loaded_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  rows_count   INT,
  PRIMARY KEY (table_name, s3_key),
  KEY idx_ing_loaded_at (loaded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
