-- Supabase Migration: 20261106000001_harden_rls_security.sql
-- Hardening: Enable Row Level Security (RLS) on all tables, restrict anon public access,
-- grant backend access to service_role, and purge default commercial test keys.

-- 1. Enable Row Level Security (RLS) on all tables
ALTER TABLE public.licenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activation_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.free_key_claims ENABLE ROW LEVEL SECURITY;

-- 2. Revoke all privileges from public / unauthenticated roles
REVOKE ALL ON TABLE public.licenses FROM anon, authenticated, public;
REVOKE ALL ON TABLE public.activation_logs FROM anon, authenticated, public;
REVOKE ALL ON TABLE public.payments FROM anon, authenticated, public;
REVOKE ALL ON TABLE public.free_key_claims FROM anon, authenticated, public;

-- 3. Grant full privileges strictly to service_role (used by secure backend / Cloudflare Worker)
GRANT ALL ON TABLE public.licenses TO service_role;
GRANT ALL ON TABLE public.activation_logs TO service_role;
GRANT ALL ON TABLE public.payments TO service_role;
GRANT ALL ON TABLE public.free_key_claims TO service_role;

-- 4. Create explicit RLS policies for service_role
DROP POLICY IF EXISTS "service_role_licenses_all" ON public.licenses;
CREATE POLICY "service_role_licenses_all"
ON public.licenses
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_activation_logs_all" ON public.activation_logs;
CREATE POLICY "service_role_activation_logs_all"
ON public.activation_logs
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_payments_all" ON public.payments;
CREATE POLICY "service_role_payments_all"
ON public.payments
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

DROP POLICY IF EXISTS "service_role_free_key_claims_all" ON public.free_key_claims;
CREATE POLICY "service_role_free_key_claims_all"
ON public.free_key_claims
FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- 5. Neutralize and delete default active commercial keys
DELETE FROM public.licenses WHERE key IN ('LIFE-VIP-9999', 'PRO30D-TEST-MONTH');
