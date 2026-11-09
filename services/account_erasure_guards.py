"""Write fences for confirmed erasure; installed explicitly before activation."""
from services import account_erasure_policy as policy

SQL = r"""
CREATE OR REPLACE FUNCTION sylvex_erasure_ascii_decode(value TEXT) RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE part TEXT[]; result TEXT := value; number INTEGER; round INTEGER;
BEGIN
    FOR round IN 1..2 LOOP
        FOR part IN SELECT regexp_matches(result, '%([0-7][0-9a-fA-F])', 'g') LOOP
            number := ('x' || part[1])::bit(8)::int;
            IF number > 0 THEN
                result := replace(result, '%' || part[1], chr(number));
            END IF;
        END LOOP;
    END LOOP;
    RETURN result;
END $$;

CREATE OR REPLACE FUNCTION sylvex_erasure_reference_keys(document JSONB, nesting INTEGER DEFAULT 0)
RETURNS TEXT[] LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE item JSONB; text_value TEXT; token TEXT[]; parts TEXT[];
        result TEXT[] := ARRAY[]::TEXT[]; nested JSONB; i INTEGER;
BEGIN
    IF document IS NULL OR nesting > 8 THEN RETURN result; END IF;
    FOR item IN SELECT jsonb_path_query(document, '$.** ? (@.type() == "string")') LOOP
        text_value := item #>> '{}';
        IF left(ltrim(text_value),1) IN ('[','{') THEN
            BEGIN
                nested := text_value::jsonb;
                result := result || sylvex_erasure_reference_keys(nested,nesting+1);
            EXCEPTION WHEN invalid_text_representation THEN
                NULL;
            END;
        END IF;
        text_value := sylvex_erasure_ascii_decode(text_value);
        IF length(text_value) <= 2048 AND text_value ~ '^[A-Za-z0-9_.~+-]+$' THEN
            result := array_append(result,text_value);
        END IF;
        FOR token IN SELECT regexp_matches(text_value,
                '[A-Za-z0-9_.%~+-]+(?:/[A-Za-z0-9_.%~+-]+)+', 'g') LOOP
            -- An object key is at most 1024 bytes; a longer slash run is
            -- inline data (base64 contains '/'), whose suffixes would grow
            -- quadratically. Keys sit in the last parts of a URL path.
            CONTINUE WHEN length(token[1]) > 2048;
            parts := string_to_array(token[1],'/');
            FOR i IN greatest(1,cardinality(parts)-16)..cardinality(parts)-1 LOOP
                result := array_append(result,array_to_string(parts[i:cardinality(parts)],'/'));
            END LOOP;
        END LOOP;
    END LOOP;
    RETURN ARRAY(SELECT DISTINCT value FROM unnest(result) value ORDER BY value);
END $$;

CREATE OR REPLACE FUNCTION sylvex_erasure_write_guard() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
DECLARE document JSONB := to_jsonb(NEW); owner_column TEXT; owner_value TEXT; owner_values TEXT[];
        keys TEXT[]; candidate_key TEXT; r RECORD; internal_request TEXT;
BEGIN
    internal_request := current_setting('sylvex.erasure_request',true);
    FOREACH owner_column IN ARRAY string_to_array(TG_ARGV[0],',') LOOP
        owner_values := ARRAY[document->>owner_column];
        IF TG_OP='UPDATE' THEN
            owner_values := owner_values || ARRAY[to_jsonb(OLD)->>owner_column];
        END IF;
        FOR owner_value IN SELECT DISTINCT value FROM unnest(owner_values) value WHERE value IS NOT NULL ORDER BY value LOOP
        IF owner_column IN ('account_id','requester_account_id') THEN
            PERFORM pg_advisory_xact_lock_shared(61180,hashtext(owner_value));
        ELSE
            PERFORM pg_advisory_xact_lock_shared(61181,hashtext(owner_value));
        END IF;
        FOR r IN SELECT request_id,state FROM sylvex_erasure_requests
            WHERE CASE WHEN owner_column IN ('account_id','requester_account_id')
                THEN account_id::text=owner_value ELSE subject_key::text=owner_value END
        LOOP
            IF internal_request IS NOT DISTINCT FROM r.request_id::text THEN CONTINUE; END IF;
            IF TG_TABLE_NAME='users' THEN
                IF COALESCE(document->>'username','')<>'' OR COALESCE(document->>'first_name','')<>'' THEN
                    IF TG_OP='INSERT' OR document->>'username' IS DISTINCT FROM to_jsonb(OLD)->>'username'
                       OR document->>'first_name' IS DISTINCT FROM to_jsonb(OLD)->>'first_name' THEN
                        RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='account_erasure_in_progress';
                    END IF;
                END IF;
                CONTINUE;
            END IF;
            IF TG_TABLE_NAME='generation_reservations' AND TG_OP='UPDATE' THEN CONTINUE; END IF;
            IF (TG_TABLE_NAME='sylvex_accounts' AND TG_OP='INSERT')
               OR TG_TABLE_NAME IN ('account_emails','account_oauth','account_link_codes','account_deletion_codes')
               OR (TG_OP='INSERT' AND TG_TABLE_NAME IN ('prostudio_generation_jobs','generation_reservations'))
               OR r.state IN ('purging','complete') THEN
                RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='account_erasure_in_progress';
            END IF;
        END LOOP;
        END LOOP;
    END LOOP;
    keys := sylvex_erasure_reference_keys(document);
    FOREACH candidate_key IN ARRAY keys LOOP
        PERFORM pg_advisory_xact_lock_shared(61182,hashtext(candidate_key));
        IF EXISTS(SELECT 1 FROM sylvex_erasure_media m
                  WHERE m.object_key=candidate_key AND m.state IN ('deleting','deleted')
                    AND (internal_request IS NULL OR internal_request<>m.request_id::text)) THEN
            RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='erased_media_reference';
        END IF;
    END LOOP;
    RETURN NEW;
END $$;
"""


def guarded_tables():
    guarded = {**policy.PERSONAL, **policy.REVIEW,
               "prostudio_generation_jobs": ("telegram_id",),
               "generation_reservations": ("telegram_id",),
               "users": ("telegram_id",), "sylvex_accounts": ("account_id",),
               "account_emails": ("account_id",), "account_oauth": ("account_id",),
               "account_link_codes": ("account_id",), "account_deletion_codes": ("account_id",),
               "site_visitors": ("account_id",)}
    for table in policy.SHARED_CATALOG | {"prostudio_media_outbox", "support_messages"}:
        guarded.setdefault(table, ())
    return guarded


def install(cur):
    from services.account_erasure import columns, ident
    schema = columns(cur)
    cur.execute(SQL)
    guarded = guarded_tables()
    installed = []
    for table, owners in guarded.items():
        if table not in schema:
            continue
        active = [column for column in owners if column in schema[table]]
        cur.execute("DROP TRIGGER IF EXISTS sylvex_erasure_guard ON " + ident(table))
        # All inserted owner names are static policy identifiers, not input.
        owner_argument = ",".join(active)
        cur.execute("CREATE TRIGGER sylvex_erasure_guard BEFORE INSERT OR UPDATE ON " + ident(table) +
                    " FOR EACH ROW EXECUTE FUNCTION sylvex_erasure_write_guard(%s)", (owner_argument,))
        installed.append(table)
    cur.execute("""CREATE TABLE IF NOT EXISTS sylvex_erasure_runtime (
        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
        guards_version INTEGER NOT NULL, installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        ownership_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    cur.execute("ALTER TABLE sylvex_erasure_runtime ADD COLUMN IF NOT EXISTS ownership_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
    cur.execute("INSERT INTO sylvex_erasure_runtime(singleton,guards_version) VALUES(TRUE,2) "
                "ON CONFLICT(singleton) DO UPDATE SET guards_version=2,installed_at=NOW()")
    return installed


def refresh_functions(cur):
    """Re-create the guard functions (CREATE OR REPLACE; triggers unchanged)."""
    cur.execute(SQL)


def require_installed(cur, *, verify_coverage=False):
    from services.account_erasure import ErasureError
    cur.execute("SELECT to_regclass('sylvex_erasure_runtime')")
    if cur.fetchone()[0] is None:
        raise ErasureError("erasure_guards_not_installed", 503)
    cur.execute("SELECT guards_version FROM sylvex_erasure_runtime WHERE singleton=TRUE")
    row = cur.fetchone()
    if not row or row[0] != 2:
        raise ErasureError("erasure_guards_not_installed", 503)
    if verify_coverage:
        from services.account_erasure import columns
        expected=set(guarded_tables()) & set(columns(cur))
        cur.execute("SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() "
                    "AND t.tgname='sylvex_erasure_guard' AND NOT t.tgisinternal AND t.tgenabled IN ('O','A')")
        installed={row[0] for row in cur.fetchall()}
        if expected-installed:
            raise ErasureError("erasure_guards_incomplete",503)
