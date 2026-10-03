"""Chain every audit event to the one before it, in the database.

Before: ``previous_hash`` was never filled in and many writers set no hash at all, so the trail was append-only
(``audit_events_immutable``) but not tamper-evident. Now a ``BEFORE INSERT`` trigger chains every row, whoever
writes it: it takes a per-organization advisory lock, gives the row the next ``chain_seq`` for its organization,
links ``previous_hash`` to the previous row's ``event_hash`` and sets ``event_hash`` to the SHA-256 of the row's
canonical content (``mdarix_audit_canonical``). Values supplied by the application are ignored.

``mdarix_verify_audit_chain(tenant, after_seq, after_hash)`` recomputes the chain from a point (the start, or a
previously verified anchor) and returns the first broken sequence number, if any. The scheduler runs it daily and
keeps each organization's last verified head as an anchor (backend/app/audit_chain.py).

Deleting an organization's data as a whole (trial deletion, offboarding: backend/app/tenant_purge.py) is the one
exception to "never delete": the immutability trigger allows deleting audit rows only of an organization whose status
is PURGING, in system scope, and only when the transaction names it in ``mdarix.audit_purge_tenant``. Updates are
always refused.

Existing rows are chained once here, in creation order per organization. Row-level security is not forced during
that backfill so the table owner sees every organization's rows; the immutability trigger is paused only for it.
"""

from alembic import op

revision = "md18auditchain"
down_revision = "md17aicontrols"
branch_labels = None
depends_on = None

# The fields a hash covers, as one canonical JSON text (jsonb output is deterministic; the time is fixed to UTC).
CANONICAL = """
CREATE OR REPLACE FUNCTION public.mdarix_audit_canonical(
    p_id uuid, p_tenant uuid, p_seq bigint, p_previous text, p_actor text, p_action text, p_entity_type text,
    p_entity_id uuid, p_correlation text, p_details jsonb, p_source_ip text, p_user_agent text, p_reason text,
    p_old jsonb, p_new jsonb, p_created timestamptz)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_build_object(
    'id', p_id, 'tenant_id', p_tenant, 'chain_seq', p_seq, 'previous_hash', p_previous,
    'actor_ref', p_actor, 'action', p_action, 'entity_type', p_entity_type, 'entity_id', p_entity_id,
    'correlation_id', p_correlation, 'details', p_details, 'source_ip', p_source_ip, 'user_agent', p_user_agent,
    'reason', p_reason, 'old_values', p_old, 'new_values', p_new,
    'created_at', to_char(p_created AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  )::text
$$;
"""

HASH_OF = (
    "encode(sha256(convert_to(public.mdarix_audit_canonical("
    "{r}.id, {r}.tenant_id, {seq}, {prev}, {r}.actor_ref, {r}.action, {r}.entity_type, {r}.entity_id, "
    "{r}.correlation_id, {r}.details, {r}.source_ip, {r}.user_agent, {r}.reason, {r}.old_values, {r}.new_values, "
    "{r}.created_at), 'UTF8')), 'hex')"
)

TRIGGER = f"""
CREATE OR REPLACE FUNCTION public.mdarix_chain_audit_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  last_seq bigint;
  last_hash text;
BEGIN
  IF NEW.id IS NULL THEN NEW.id := gen_random_uuid(); END IF;
  IF NEW.created_at IS NULL THEN NEW.created_at := now(); END IF;
  -- One writer per organization at a time, until its transaction ends, so the chain never forks.
  PERFORM pg_advisory_xact_lock(hashtextextended('mdarix_audit_chain:' || NEW.tenant_id::text, 0));
  SELECT chain_seq, event_hash INTO last_seq, last_hash
    FROM public.audit_events
   WHERE tenant_id = NEW.tenant_id
   ORDER BY chain_seq DESC
   LIMIT 1;
  NEW.chain_seq := COALESCE(last_seq, 0) + 1;
  NEW.previous_hash := last_hash;
  NEW.event_hash := {HASH_OF.format(r="NEW", seq="NEW.chain_seq", prev="NEW.previous_hash")};
  RETURN NEW;
END $$;
"""

VERIFY = f"""
CREATE OR REPLACE FUNCTION public.mdarix_verify_audit_chain(
    p_tenant uuid, p_after_seq bigint DEFAULT 0, p_after_hash text DEFAULT NULL)
RETURNS TABLE(checked bigint, first_broken_seq bigint, last_seq bigint, last_hash text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  r record;
  previous text := p_after_hash;
  expected bigint := p_after_seq;
  broken bigint := NULL;
BEGIN
  checked := 0;
  FOR r IN
    SELECT * FROM public.audit_events WHERE tenant_id = p_tenant AND chain_seq > p_after_seq ORDER BY chain_seq
  LOOP
    expected := expected + 1;
    checked := checked + 1;
    IF broken IS NULL AND (
         r.chain_seq <> expected
         OR r.previous_hash IS DISTINCT FROM previous
         OR r.event_hash IS DISTINCT FROM {HASH_OF.format(r="r", seq="r.chain_seq", prev="r.previous_hash")}
       ) THEN
      broken := r.chain_seq;
    END IF;
    previous := r.event_hash;
  END LOOP;
  first_broken_seq := broken;
  last_seq := expected;
  last_hash := previous;
  RETURN NEXT;
END $$;
"""

BACKFILL = f"""
DO $$
DECLARE
  r record;
  current_tenant uuid := NULL;
  previous text;
  seq bigint;
  digest text;
BEGIN
  FOR r IN SELECT * FROM public.audit_events ORDER BY tenant_id, created_at, id LOOP
    IF current_tenant IS DISTINCT FROM r.tenant_id THEN
      current_tenant := r.tenant_id;
      previous := NULL;
      seq := 0;
    END IF;
    seq := seq + 1;
    digest := {HASH_OF.format(r="r", seq="seq", prev="previous")};
    UPDATE public.audit_events SET chain_seq = seq, previous_hash = previous, event_hash = digest WHERE id = r.id;
    previous := digest;
  END LOOP;
END $$;
"""


IMMUTABLE_WITH_PURGE = """
CREATE OR REPLACE FUNCTION public.mdarix_reject_audit_mutation() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE'
     AND current_setting('mdarix.audit_purge_tenant', true) = OLD.tenant_id::text
     AND (SELECT public.mdarix_system_scope())
     AND EXISTS (SELECT 1 FROM public.tenants WHERE id = OLD.tenant_id AND status = 'PURGING') THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'audit_events are immutable and append-only';
END;
$$ LANGUAGE plpgsql;
"""

IMMUTABLE_ORIGINAL = """
CREATE OR REPLACE FUNCTION public.mdarix_reject_audit_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_events are immutable and append-only';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade():
    op.execute("ALTER TABLE public.audit_events ADD COLUMN chain_seq bigint")
    op.execute(CANONICAL)
    op.execute("ALTER TABLE public.audit_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_immutable")
    op.execute(BACKFILL)
    op.execute("ALTER TABLE public.audit_events ENABLE TRIGGER audit_events_immutable")
    op.execute("ALTER TABLE public.audit_events FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.audit_events ALTER COLUMN chain_seq SET NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_audit_events_tenant_chain ON public.audit_events (tenant_id, chain_seq)")
    op.execute(TRIGGER)
    op.execute(
        "CREATE TRIGGER audit_events_chain BEFORE INSERT ON public.audit_events "
        "FOR EACH ROW EXECUTE FUNCTION public.mdarix_chain_audit_event()"
    )
    op.execute(VERIFY)
    op.execute(IMMUTABLE_WITH_PURGE)
    for role in ("mdarix_runtime", "mdarix_readonly"):
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
            f"GRANT EXECUTE ON FUNCTION public.mdarix_verify_audit_chain(uuid, bigint, text) TO {role}; "
            f"GRANT EXECUTE ON FUNCTION public.mdarix_audit_canonical(uuid, uuid, bigint, text, text, text, text, "
            f"uuid, text, jsonb, text, text, text, jsonb, jsonb, timestamptz) TO {role}; END IF; END $$;"
        )


def downgrade():
    op.execute(IMMUTABLE_ORIGINAL)
    op.execute("DROP TRIGGER IF EXISTS audit_events_chain ON public.audit_events")
    op.execute("DROP FUNCTION IF EXISTS public.mdarix_chain_audit_event()")
    op.execute("DROP FUNCTION IF EXISTS public.mdarix_verify_audit_chain(uuid, bigint, text)")
    op.execute("DROP INDEX IF EXISTS public.uq_audit_events_tenant_chain")
    op.execute("ALTER TABLE public.audit_events DROP COLUMN IF EXISTS chain_seq")
    op.execute(
        "DROP FUNCTION IF EXISTS public.mdarix_audit_canonical(uuid, uuid, bigint, text, text, text, text, uuid, "
        "text, jsonb, text, text, text, jsonb, jsonb, timestamptz)"
    )
