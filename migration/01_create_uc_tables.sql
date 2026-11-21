-- ============================================================================
-- InfraGov — Unity Catalog DDL (Azure Databricks)
-- Target schema: prd_mega.sgpbpi163
-- Generated from services/schema.py — keep the two in sync.
-- Run in a Databricks SQL editor as a user with CREATE TABLE on the schema.
-- ============================================================================

USE CATALOG prd_mega;
USE SCHEMA sgpbpi163;

-- Volume that replaces the Supabase Storage bucket 'assessment-documents'
CREATE VOLUME IF NOT EXISTS prd_mega.sgpbpi163.infragov_documents
  COMMENT 'InfraGov source documents (migrated from Supabase Storage)';

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_users (
  id STRING NOT NULL COMMENT 'UUID; same value as Supabase auth.users.id / profiles.id',
  email STRING NOT NULL COMMENT 'Lower-case login e-mail (unique)',
  password_hash STRING COMMENT 'argon2id hash; migrated bcrypt ($2a$) hashes are re-hashed on next login',
  name STRING NOT NULL,
  organisation STRING NOT NULL,
  country STRING NOT NULL,
  job_title STRING NOT NULL,
  phone STRING NOT NULL COMMENT 'Encrypted at rest (AES-256-GCM, prefix enc:v1:)',
  role STRING NOT NULL COMMENT 'Admin | Owner | Contributor | Reviewer | Viewer',
  pref_email_notifications BOOLEAN NOT NULL,
  pref_weekly_digest BOOLEAN NOT NULL,
  pref_invite_notifications BOOLEAN NOT NULL,
  pref_publication_notifications BOOLEAN NOT NULL,
  is_active BOOLEAN NOT NULL COMMENT 'False = account disabled',
  email_confirmed_at TIMESTAMP,
  failed_login_count INT NOT NULL COMMENT 'Consecutive failed logins (lockout)',
  locked_until TIMESTAMP COMMENT 'Temporary lockout end',
  last_login_at TIMESTAMP,
  password_changed_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_users_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Platform users (replaces Supabase auth.users + public.profiles).'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_users ADD CONSTRAINT role_valid CHECK (role IN ('Admin','Owner','Contributor','Reviewer','Viewer'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_user_sessions (
  session_hash STRING NOT NULL COMMENT 'SHA-256 of the random session id held in the signed cookie',
  user_id STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  last_seen_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL COMMENT 'Absolute expiry',
  user_agent STRING NOT NULL COMMENT 'Truncated user agent',
  revoked_at TIMESTAMP,
  CONSTRAINT infragov_user_sessions_pk PRIMARY KEY (session_hash)
)
USING DELTA
COMMENT 'Server-side login sessions (only a SHA-256 of the session id is stored).'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_auth_tokens (
  token_hash STRING NOT NULL COMMENT 'SHA-256 of the token sent by e-mail',
  user_id STRING NOT NULL,
  purpose STRING NOT NULL COMMENT 'reset | invite',
  created_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL,
  used_at TIMESTAMP,
  CONSTRAINT infragov_auth_tokens_pk PRIMARY KEY (token_hash)
)
USING DELTA
COMMENT 'Single-use password reset / set-password tokens (hash only).'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_auth_tokens ADD CONSTRAINT purpose_valid CHECK (purpose IN ('reset','invite'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_assessments (
  id STRING NOT NULL COMMENT 'UUID',
  kind STRING NOT NULL COMMENT 'infragov | pagfa',
  title STRING NOT NULL,
  country STRING NOT NULL,
  department STRING NOT NULL,
  description STRING,
  fiscal_years STRING NOT NULL COMMENT 'JSON array of FY labels, e.g. ["25/26"]',
  owner_user_id STRING NOT NULL COMMENT 'FK → infragov_users.id',
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_assessments_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Top-level assessment container (one per country / framework / FY).'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_assessments ADD CONSTRAINT kind_valid CHECK (kind IN ('infragov','pagfa'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_dimensions (
  id STRING NOT NULL COMMENT 'UUID',
  assessment_id STRING NOT NULL COMMENT 'FK → infragov_assessments.id',
  dim_id INT NOT NULL COMMENT '1-16 (InfraGov) or 1-8 (PAG-FA)',
  status STRING NOT NULL COMMENT 'Draft | Validated | Published',
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_dimensions_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT '16 InfraGov dimensions / 8 PAG-FA pillars per assessment.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_dimensions ADD CONSTRAINT status_valid CHECK (status IN ('Draft','Validated','Published'));
ALTER TABLE prd_mega.sgpbpi163.infragov_dimensions ADD CONSTRAINT dim_range CHECK (dim_id BETWEEN 1 AND 16);

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_mbi_entries (
  id STRING NOT NULL COMMENT 'UUID',
  dimension_id STRING NOT NULL COMMENT 'FK → infragov_dimensions.id',
  assessment_id STRING NOT NULL COMMENT 'Denormalised FK → infragov_assessments.id (new column)',
  mbi_code STRING NOT NULL COMMENT 'e.g. D3.2',
  key_respondents STRING NOT NULL COMMENT 'JSON array of strings',
  data_source STRING NOT NULL,
  result_summary STRING NOT NULL,
  result_detail STRING NOT NULL COMMENT 'Internal-only; encrypted at rest (enc:v1:)',
  maturity_benchmark STRING COMMENT 'Incipient | Nascent | Emerging | Advanced',
  score INT COMMENT '1-4',
  files STRING NOT NULL COMMENT 'JSON array of attached file names',
  status STRING NOT NULL COMMENT 'complete | in-progress | untouched',
  last_edited_by STRING COMMENT 'FK → infragov_users.id',
  last_edited_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_mbi_entries_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Indicator (MBI) answers.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_mbi_entries ADD CONSTRAINT score_range CHECK (score IS NULL OR score BETWEEN 1 AND 4);
ALTER TABLE prd_mega.sgpbpi163.infragov_mbi_entries ADD CONSTRAINT status_valid CHECK (status IN ('complete','in-progress','untouched'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_comments (
  id STRING NOT NULL COMMENT 'UUID',
  assessment_id STRING NOT NULL,
  dimension_id STRING NOT NULL,
  mbi_code STRING COMMENT 'NULL for dimension-level threads',
  author_user_id STRING NOT NULL,
  author_name STRING NOT NULL,
  text STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP COMMENT 'Set when edited',
  CONSTRAINT infragov_comments_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Dimension-level and per-indicator comment threads.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_activity_log (
  id STRING NOT NULL COMMENT 'UUID',
  assessment_id STRING NOT NULL,
  type STRING NOT NULL COMMENT 'activity type, e.g. mbi.updated',
  actor_user_id STRING NOT NULL,
  actor_name STRING NOT NULL,
  actor_organisation STRING,
  target_user_id STRING,
  target_name STRING,
  dim_id INT,
  dimension_name STRING,
  dimension_ids STRING COMMENT 'JSON array of ints',
  mbi_code STRING,
  fields_changed STRING COMMENT 'JSON array of strings',
  import_source STRING COMMENT 'docx | pdf',
  document_name STRING,
  ai_assisted BOOLEAN NOT NULL,
  from_role STRING,
  to_role STRING,
  reason STRING,
  review_note STRING,
  request_id STRING,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_activity_log_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Audit trail per assessment.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_dimension_collaborators (
  id STRING NOT NULL COMMENT 'UUID',
  dimension_id STRING NOT NULL,
  assessment_id STRING NOT NULL COMMENT 'Denormalised (new column)',
  user_id STRING NOT NULL,
  role STRING NOT NULL COMMENT 'Contributor | Reviewer | Viewer',
  invited_by STRING NOT NULL,
  invited_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_dimension_collaborators_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Per-dimension role assignments.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_dimension_collaborators ADD CONSTRAINT role_valid CHECK (role IN ('Contributor','Reviewer','Viewer'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_dimension_invitations (
  id STRING NOT NULL COMMENT 'UUID',
  token_hash STRING NOT NULL COMMENT 'SHA-256 of the invitation token (Supabase stored plaintext)',
  assessment_id STRING NOT NULL,
  dimension_id STRING NOT NULL,
  email STRING NOT NULL COMMENT 'Invitee e-mail; must match the accepting account',
  role STRING NOT NULL,
  organisation STRING,
  invited_by STRING NOT NULL,
  status STRING NOT NULL COMMENT 'Pending | Accepted | Revoked | Expired',
  accepted_user_id STRING,
  accepted_at TIMESTAMP,
  expires_at TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_dimension_invitations_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Pending per-dimension invitations (token stored as SHA-256 only).'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_dimension_invitations ADD CONSTRAINT status_valid CHECK (status IN ('Pending','Accepted','Revoked','Expired'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_assessment_team (
  id STRING NOT NULL COMMENT 'UUID',
  assessment_id STRING NOT NULL,
  user_id STRING NOT NULL,
  role STRING NOT NULL COMMENT 'Owner | Contributor | Reviewer | Viewer',
  organisation STRING,
  joined_at TIMESTAMP NOT NULL,
  last_activity TIMESTAMP NOT NULL,
  CONSTRAINT infragov_assessment_team_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Denormalised team list per assessment.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_unpublish_requests (
  id STRING NOT NULL COMMENT 'UUID',
  assessment_id STRING NOT NULL,
  dimension_id STRING NOT NULL,
  requested_by_user_id STRING NOT NULL,
  requested_by_name STRING NOT NULL,
  requested_by_email STRING NOT NULL,
  reason STRING NOT NULL,
  status STRING NOT NULL COMMENT 'Pending | Approved | Denied',
  reviewed_by_user_id STRING,
  reviewed_by_name STRING,
  reviewed_at TIMESTAMP,
  review_note STRING,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_unpublish_requests_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Owner-initiated unpublish requests awaiting Admin review.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_unpublish_requests ADD CONSTRAINT status_valid CHECK (status IN ('Pending','Approved','Denied'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_assessment_documents (
  id STRING NOT NULL COMMENT 'UUID',
  assessment_id STRING NOT NULL,
  filename STRING NOT NULL COMMENT 'Sanitised original file name',
  mime_type STRING,
  size_bytes BIGINT NOT NULL,
  storage_path STRING NOT NULL COMMENT 'Path inside the UC Volume',
  sha256 STRING COMMENT 'Content hash (integrity)',
  status STRING NOT NULL COMMENT 'processing | ready | failed',
  error STRING,
  extracted_text STRING COMMENT 'Encrypted at rest (enc:v1:)',
  char_count INT,
  page_count INT,
  uploaded_by_user_id STRING,
  uploaded_by_name STRING NOT NULL,
  uploaded_by_organisation STRING,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_assessment_documents_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Source documents; files live in the UC Volume infragov_documents.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_assessment_documents ADD CONSTRAINT status_valid CHECK (status IN ('processing','ready','failed'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_indicator_suggestions (
  id STRING NOT NULL COMMENT 'UUID',
  assessment_id STRING NOT NULL,
  dimension_id STRING NOT NULL,
  dim_id INT NOT NULL,
  mbi_id INT NOT NULL COMMENT '1-based indicator number',
  status STRING NOT NULL COMMENT 'suggested | no_evidence',
  suggestion STRING COMMENT 'JSON draft (was JSONB)',
  reason STRING,
  locale STRING NOT NULL,
  model STRING,
  document_ids STRING NOT NULL COMMENT 'JSON array of document ids',
  drafted_by STRING,
  drafted_by_name STRING,
  drafted_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_indicator_suggestions_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Saved AI 'Suggest Responses' drafts.'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');
ALTER TABLE prd_mega.sgpbpi163.infragov_indicator_suggestions ADD CONSTRAINT status_valid CHECK (status IN ('suggested','no_evidence'));

CREATE TABLE IF NOT EXISTS prd_mega.sgpbpi163.infragov_security_events (
  id STRING NOT NULL COMMENT 'UUID',
  event_type STRING NOT NULL COMMENT 'login.success | login.failure | lockout | ...',
  user_id STRING,
  ip_hash STRING COMMENT 'Keyed hash of the client IP (no raw IPs stored)',
  detail STRING,
  created_at TIMESTAMP NOT NULL,
  CONSTRAINT infragov_security_events_pk PRIMARY KEY (id)
)
USING DELTA
COMMENT 'Security audit trail (logins, lockouts, admin actions).'
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

