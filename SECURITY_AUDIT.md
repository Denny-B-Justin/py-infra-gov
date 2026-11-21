# Security audit — InfraGov Assessment Tool

Scope: the original Next.js + Supabase repository (`infragov-dashboard-main`) and the
Python Dash rewrite in this folder. Each finding lists where it was found, the impact,
and how the Dash version addresses it. Date of review: 19 Nov 2026.

## 1. Findings in the original Next.js / Supabase app

| # | Severity | Finding | Where | Fix in the Dash version |
|---|----------|---------|-------|-------------------------|
| C1 | **Critical** | Every invitation row (token + invitee e-mail) is readable by **anonymous** users: `CREATE POLICY "Anyone can read invitations by token" … TO anon, authenticated USING (true)`. With the public anon key anyone can list all tokens and join any dimension. | `supabase/schema/002_assessments_and_data.sql` | Tokens are stored only as SHA-256 hashes; lookup is by hash; nothing lists invitations except the Owner/Admin. |
| C2 | **Critical** | Accepting an invitation does not check that the signed-in user is the invited e-mail, nor expiry/status. Anyone holding a link gets the role. | `lib/supabase/collaboration.ts` `acceptInvitationInSupabase` | Invite bound to the invited e-mail, `Pending` status and `expires_at` enforced server-side (`repository.accept_invitation`). |
| H1 | High | Business rules enforced only in the browser: an Owner can set a dimension straight from Published → Draft through the Supabase API (bypassing Admin approval), and can publish incomplete dimensions. | RLS `"Owners and Admins can update dimensions"`; `lib/store.ts` | Publish requires completeness on the server; direct unpublish is Admin-only; Owners must file a request. |
| H2 | High | Over-broad reads (`USING (true)` for any signed-in user) on `profiles` (every user's e-mail, phone, role), `assessments`, `dimensions`, `activity_log` (names, organisations, unpublish reasons), `dimension_collaborators`, `assessment_team`, `unpublish_requests`. Users can see data that isn't theirs. | `001`, `002` schema | Reads are scoped to membership: team/activity/invitations only for members/managers; user directory Admin-only; non-members see only **published** answers. |
| H3 | High | "Internal-only" Result Detail is returned by the database to Reviewers/Viewers and on published dimensions — it is only hidden in the UI. | RLS on `mbi_entries` | Stripped server-side unless Admin/Owner/Contributor on that dimension; encrypted at rest (AES-256-GCM). |
| H4 | High | UPDATE policies without `WITH CHECK` (`mbi_entries`, `assessments`, `comments`): a contributor can re-point an entry/comment to another dimension or assessment; an Owner can rewrite `owner_user_id`. | `002`, `004` schema | Keys are always built on the server from validated ids; clients never send foreign keys. |
| H5 | High | Any signed-in user can INSERT arbitrary `activity_log` rows into any assessment (only `actor_user_id = auth.uid()` is checked) — audit-trail forgery. | `002` schema | Only the server writes activity, after an authorised action. |
| H6 | High | `/api/refine` only requires a login (any Viewer can spend the Anthropic budget); no rate limits on AI routes. | `app/api/refine/route.ts` | Edit permission on the dimension required; per-user hourly limit. |
| M1 | Medium | Links built from the request host (`request.nextUrl.origin`, `window.location.origin`) → host-header / link poisoning. | `app/api/admin/invites/route.ts`, forgot-password page | Links use the configured `APP_BASE_URL` only. |
| M2 | Medium | No security headers (CSP, HSTS, frame-ancestors, nosniff, Referrer-Policy, Permissions-Policy). | `next.config.ts` | Full header set; CSP allows scripts only from `'self'` + hashes of Dash's bootstrap. |
| M3 | Medium | Account page: profile/preference edits never saved; change-password is a stub; weak password minimums (6–8 chars). | `app/[locale]/account/page.tsx`, `lib/store.ts` | Persisted; current password verified; 12+ char policy with complexity and common-password checks; other sessions revoked. |
| M4 | Medium | `SECURITY DEFINER` functions without `SET search_path` (Supabase lint 0011). | `001`, `002` schema | Not applicable after migration (no definer functions). If you keep Supabase, add `SET search_path = public`. |
| M5 | Medium | Session + profile (e-mail, phone, role) persisted in `localStorage` by zustand — readable by any injected script / shared computers. | `lib/store.ts` (`persist`) | Server-side sessions; HttpOnly + Secure + SameSite cookie with only a random id; nothing stored in browser storage. |
| M6 | Medium | Uploads trusted the declared MIME type; no zip-bomb guard before parsing Office files. | Storage bucket config, `extractDocumentText.ts` | Extension + magic-byte checks, 50 MB cap, uncompressed-size guard, sanitised names, server-generated paths, `Content-Disposition: attachment`. |
| M7 | Medium | CSV exports vulnerable to spreadsheet formula injection (`=`, `+`, `-`, `@`). | `lib/exports.ts`, country page | Cells neutralised before export. |
| L1 | Low | `dangerouslySetInnerHTML` (static strings today, but an XSS sink). | account page | Removed — all text rendered as text. |
| L2 | Low | No app-level brute-force protection (relied on Supabase defaults). | login | Per-IP throttle + per-account lockout (5 failures → 15 min), generic errors, constant-time dummy hash for unknown users. |
| L3 | Low | Invite flow redirects unknown users to `/register`, which is disabled — invitations can't be completed. | `join/[token]/page.tsx` | Invites now require an account (Admin creates users) and then work end to end. |
| L4 | Low | AI prompt injection via uploaded documents. | `lib/server/suggestIndicator.ts` | Documents framed as untrusted data, outputs length-clamped, nothing saved without human review. |
| ✓ | Info | No secrets committed; `.env*` git-ignored; service-role key used only server-side behind an Admin check; only `/public` is web-served. | — | Same posture kept; plus `.rscignore`, blocked dotfiles/source paths. |

## 2. Controls implemented in the Dash version (your checklist)

| Requirement | Implementation |
|---|---|
| **Constants** | `constants.py` (tables, UC location, roles, limits, env-driven settings); page copy in `pages/pages_constants.py`. Table names are validated identifiers. |
| **Sanitize fonts** | Inter + Fira Sans **self-hosted** in `assets/fonts` (OFL licences included); no Google Fonts / CDN requests; CSP `font-src 'self'`. All Dash JS/CSS served locally (`serve_locally=True`). |
| **Secure the database** | Service principal with least privilege (`migration/02_grants_least_privilege.sql`); TLS-only connector with certificate verification; no DDL rights for the app; audit trail in `infragov_security_events`. |
| **Hash passwords** | Argon2id (`argon2-cffi`, t=3, m=46 MiB). Supabase bcrypt hashes are verified once and re-hashed to Argon2id at next login. Reset/invite/session tokens stored as SHA-256 only. |
| **Validate & sanitise the username field** | `services/validators.validate_email`: NFKC-normalised, lower-cased, ASCII-only allow-list regex, ≤254 chars — quotes, spaces, `;`, `--`, `<`, `>` can never pass. Verified with injection payloads. |
| **Parameterised SQL** | Every statement uses driver-bound `:named` parameters (`services/db.py`); IN-lists are generated placeholders; identifiers come only from constants and are regex-checked. |
| **Data encrypted** | In transit: HTTPS (HSTS) to users, TLS to Databricks/SMTP. At rest: ADLS/Delta platform encryption **plus** field-level AES-256-GCM for phone numbers, Result Detail and extracted document text. |
| **User vs admin login** | One sign-in for all; capability decided server-side by role (Admin / Owner / Contributor / Reviewer / Viewer). |
| **Proper authentication** | Server-side sessions, rotation on login, 30 min idle / 12 h absolute expiry, revocation on logout & password change, lockout, generic errors. |
| **Users only access their data** | `services/permissions.py` + `services/repository.py` check every read/write; tested (see §3). |
| **XSS** | React/Dash escape all text; no raw HTML rendering; release notes use a tag whitelist; strict CSP (no inline/eval scripts); Plotly hover text escaped. |
| **CORS** | No `Access-Control-*` headers ever; OPTIONS preflights refused; state-changing requests need a same-origin `Origin`/`Referer`; JSON-only callback endpoint; `SameSite=Lax` cookie. |
| **Debug off** | `debug=False`, dev tools UI/props-check off; production cannot enable it even with `DASH_DEBUG=true`; generic error pages, no tracebacks. |
| **Keys & env vars** | All secrets from environment (`.env.sample` documents them); startup refuses missing/weak `SECRET_KEY`, `FIELD_ENCRYPTION_KEY` or DB credentials in production; secrets never logged. |
| **Admin routes** | Router blocks non-Admins (logged as `authz.admin_denied`) and each admin callback re-checks the role. |
| **Exposed files** | Only `/assets` is served; requests for dotfiles, `.py`, `.env`, `.sqlite`, `manifest.json`, `requirements.txt`, source folders → 404; documents only via an authorised download route. |

## 3. Verification performed

* 43 automated checks passed (authorisation matrix, encryption at rest, Argon2id, hashed tokens, e-mail-bound invites, SQL-injection usernames, lockout, blocked files, CORS/CSRF, headers, no tracebacks).
* End-to-end browser run (headless Chrome): edit + save + autosave, comments, publish, unpublish request, Admin approval — zero console/CSP errors; an `<img onerror>` payload in a summary and a comment rendered as plain text and never executed.
* `pip-audit` on the full pinned dependency tree: **no known vulnerabilities**.

## 4. Residual items / recommendations

1. Put Posit Connect content access to "logged-in users" (or a group) as a second gate in front of the app login.
2. Configure SMTP so password resets don't require Admin-shared links.
3. Rotate the service-principal secret and `SECRET_KEY` on a schedule; keep `FIELD_ENCRYPTION_KEY` in a key vault (losing it makes encrypted columns unreadable).
4. Add MFA (Connect/IdP SSO is the simplest route) for Admin accounts.
5. Session validation is cached per process for 60 s, so a revoked session can live up to a minute on other worker processes.
