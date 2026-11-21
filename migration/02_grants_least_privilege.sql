-- ============================================================================
-- STEP 2 — Least-privilege access for the app's service principal
-- Run as the schema owner / a metastore admin. Replace <app-sp-application-id>
-- with the service principal's Application (client) ID.
--
-- The app needs to read and write rows. It does NOT need to create, alter or
-- drop tables, so it gets no CREATE / MODIFY-on-schema / MANAGE / ALL PRIVILEGES.
-- ============================================================================

GRANT USE CATALOG ON CATALOG prd_mega TO `<app-sp-application-id>`;
GRANT USE SCHEMA  ON SCHEMA  prd_mega.sgpbpi163 TO `<app-sp-application-id>`;

GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_users                   TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_user_sessions           TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_auth_tokens             TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_assessments             TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_dimensions              TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_mbi_entries             TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_comments                TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_activity_log            TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_dimension_collaborators TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_dimension_invitations   TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_assessment_team         TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_unpublish_requests      TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_assessment_documents    TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_indicator_suggestions   TO `<app-sp-application-id>`;
GRANT SELECT, MODIFY ON TABLE prd_mega.sgpbpi163.infragov_security_events         TO `<app-sp-application-id>`;

GRANT READ VOLUME, WRITE VOLUME ON VOLUME prd_mega.sgpbpi163.infragov_documents   TO `<app-sp-application-id>`;

-- The SP also needs "Can use" on the SQL warehouse (Warehouse → Permissions).

-- Recommended hardening (Databricks UI / account console):
--   * Restrict the SQL warehouse to the SP + admins; enable IP access lists.
--   * Rotate the SP OAuth secret regularly (≤ 1 year) and store it only in
--     Posit Connect "Vars" (marked secret) — never in code or manifest.json.
--   * Keep audit logs (system.access.audit) enabled for the schema.
--   * Optional: a customer-managed key (CMK) for the workspace storage.

-- Analysts who only need reporting access should get a view WITHOUT secrets:
CREATE OR REPLACE VIEW prd_mega.sgpbpi163.infragov_users_public AS
SELECT id, email, name, organisation, country, role, is_active, created_at
FROM prd_mega.sgpbpi163.infragov_users;
-- GRANT SELECT ON VIEW prd_mega.sgpbpi163.infragov_users_public TO `analysts`;
