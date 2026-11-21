-- ============================================================================
-- STEP 0 — Measure how much data you are migrating (run in Supabase SQL Editor)
-- Read-only. Returns exact row counts and on-disk sizes for every table the
-- InfraGov app uses, plus the Storage bucket that holds uploaded documents.
-- ============================================================================

-- 1) Exact row counts + table size (data + indexes + TOAST) per table
SELECT 'auth.users'                     AS source_table, (SELECT count(*) FROM auth.users)                     AS row_count, pg_size_pretty(pg_total_relation_size('auth.users'))                     AS total_size
UNION ALL SELECT 'public.profiles',               (SELECT count(*) FROM public.profiles),               pg_size_pretty(pg_total_relation_size('public.profiles'))
UNION ALL SELECT 'public.assessments',            (SELECT count(*) FROM public.assessments),            pg_size_pretty(pg_total_relation_size('public.assessments'))
UNION ALL SELECT 'public.dimensions',             (SELECT count(*) FROM public.dimensions),             pg_size_pretty(pg_total_relation_size('public.dimensions'))
UNION ALL SELECT 'public.mbi_entries',            (SELECT count(*) FROM public.mbi_entries),            pg_size_pretty(pg_total_relation_size('public.mbi_entries'))
UNION ALL SELECT 'public.comments',               (SELECT count(*) FROM public.comments),               pg_size_pretty(pg_total_relation_size('public.comments'))
UNION ALL SELECT 'public.activity_log',           (SELECT count(*) FROM public.activity_log),           pg_size_pretty(pg_total_relation_size('public.activity_log'))
UNION ALL SELECT 'public.dimension_collaborators',(SELECT count(*) FROM public.dimension_collaborators),pg_size_pretty(pg_total_relation_size('public.dimension_collaborators'))
UNION ALL SELECT 'public.dimension_invitations',  (SELECT count(*) FROM public.dimension_invitations),  pg_size_pretty(pg_total_relation_size('public.dimension_invitations'))
UNION ALL SELECT 'public.assessment_team',        (SELECT count(*) FROM public.assessment_team),        pg_size_pretty(pg_total_relation_size('public.assessment_team'))
UNION ALL SELECT 'public.unpublish_requests',     (SELECT count(*) FROM public.unpublish_requests),     pg_size_pretty(pg_total_relation_size('public.unpublish_requests'))
UNION ALL SELECT 'public.assessment_documents',   (SELECT count(*) FROM public.assessment_documents),   pg_size_pretty(pg_total_relation_size('public.assessment_documents'))
UNION ALL SELECT 'public.indicator_suggestions',  (SELECT count(*) FROM public.indicator_suggestions),  pg_size_pretty(pg_total_relation_size('public.indicator_suggestions'))
ORDER BY 1;

-- 2) Grand total of the relational data
SELECT pg_size_pretty(sum(pg_total_relation_size(format('%I.%I', schemaname, relname)::regclass))) AS total_relational_size
FROM pg_stat_user_tables
WHERE schemaname = 'public'
  AND relname IN ('profiles','assessments','dimensions','mbi_entries','comments','activity_log',
                  'dimension_collaborators','dimension_invitations','assessment_team',
                  'unpublish_requests','assessment_documents','indicator_suggestions');

-- 3) Uploaded files in Supabase Storage (they move to the UC Volume)
SELECT count(*)                                                   AS file_count,
       pg_size_pretty(coalesce(sum((metadata->>'size')::bigint), 0)) AS total_file_size,
       pg_size_pretty(coalesce(max((metadata->>'size')::bigint), 0)) AS largest_file
FROM storage.objects
WHERE bucket_id = 'assessment-documents';

-- 4) Largest text payloads (extracted document text is the biggest column)
SELECT pg_size_pretty(coalesce(sum(octet_length(extracted_text)), 0)) AS extracted_text_bytes,
       coalesce(max(char_count), 0)                                    AS largest_document_chars
FROM public.assessment_documents;

-- 5) Business-level picture
SELECT kind, count(*) AS assessments,
       (SELECT count(*) FROM public.dimensions d JOIN public.assessments a2 ON a2.id = d.assessment_id
         WHERE a2.kind = a.kind AND d.status = 'Published') AS published_dimensions
FROM public.assessments a GROUP BY kind;
