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
        pk_list TEXT; pk_column TEXT; row_ref JSONB;
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
        -- 64 lock buckets (class 61184), not one lock per key: a bulk write
        -- of many rows with many keys must not fill the shared lock table.
        -- The executor takes the same bucket exclusively per object.
        PERFORM pg_advisory_xact_lock_shared(61184,hashtext(candidate_key) & 63);
        IF EXISTS(SELECT 1 FROM sylvex_erasure_media m
                  WHERE m.object_key=candidate_key AND m.state IN ('deleting','deleted')
                    AND (internal_request IS NULL OR internal_request<>m.request_id::text)) THEN
            RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='erased_media_reference';
        END IF;
    END LOOP;
    -- Reference index (installed only by install_reference_index): the row
    -- that references an application object, in the same transaction as the
    -- write. Entries are candidates; readers re-verify the row itself.
    IF to_regclass('sylvex_storage_reference_tables') IS NOT NULL THEN
        SELECT pk_columns INTO pk_list FROM sylvex_storage_reference_tables WHERE table_name=TG_TABLE_NAME;
        IF COALESCE(pk_list,'')<>'' THEN
            row_ref := '[]'::jsonb;
            FOREACH pk_column IN ARRAY string_to_array(pk_list,',') LOOP
                row_ref := row_ref || jsonb_build_array(document->pk_column);
            END LOOP;
            INSERT INTO sylvex_storage_references(object_key,source_table,source_row)
                SELECT k,TG_TABLE_NAME,row_ref::text FROM unnest(keys) k
                WHERE left(k,10)='generated/' AND length(k)<=1024
                ON CONFLICT DO NOTHING;
        END IF;
    END IF;
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


REFERENCE_PREFIX = "generated/"
REFERENCE_MAX_KEY = 1024


def reference_tables(schema):
    """Every table _shared_reference reads (all of them carry the guard)."""
    tables = set(policy.PERSONAL) | set(policy.REVIEW) | policy.SHARED_CATALOG | {
        "prostudio_generation_jobs", "support_messages", "prostudio_media_outbox"}
    return sorted(tables & set(schema))


def primary_key(cur, table):
    cur.execute("SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey) "
                "WHERE i.indrelid=to_regclass(%s) AND i.indisprimary ORDER BY array_position(i.indkey::int2[],a.attnum)",
                (table,))
    return [row[0] for row in cur.fetchall()]


def install_reference_index(cur):
    """Migration (owner approval): reference index tables + recording.

    No trigger is dropped or re-created and no existing table is altered:
    the already installed guard function starts recording as soon as a
    table has a control row. Lookups trust a table only after its backfill.
    """
    from services.account_erasure import columns
    cur.execute("SET LOCAL lock_timeout='5s'")
    cur.execute("""CREATE TABLE IF NOT EXISTS sylvex_storage_references (
        object_key TEXT NOT NULL, source_table TEXT NOT NULL, source_row TEXT NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY(object_key,source_table,source_row))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS sylvex_storage_reference_tables (
        table_name TEXT PRIMARY KEY, pk_columns TEXT NOT NULL,
        recording_since TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        backfill_cursor TEXT, backfilled_at TIMESTAMPTZ)""")
    cur.execute(SQL)
    tables = {}
    for table in reference_tables(columns(cur)):
        tables[table] = ",".join(primary_key(cur, table))
        cur.execute("INSERT INTO sylvex_storage_reference_tables(table_name,pk_columns) VALUES(%s,%s) "
                    "ON CONFLICT(table_name) DO NOTHING", (table, tables[table]))
    return tables


def _guard_records_references(cur):
    cur.execute("SELECT p.prosrc FROM pg_proc p WHERE p.proname='sylvex_erasure_write_guard' "
                "AND p.pronamespace=(SELECT oid FROM pg_namespace WHERE nspname=current_schema())")
    row = cur.fetchone()
    return bool(row and "sylvex_storage_references" in row[0])


def invalidate_reference_index_if_unrecorded(cur):
    """Before re-creating the functions: if the installed guard does not
    record references (an older release ran), entries may be missing, so
    every table needs a new backfill before lookups trust it again."""
    cur.execute("SELECT to_regclass('sylvex_storage_reference_tables')")
    if cur.fetchone()[0] is None or _guard_records_references(cur):
        return False
    cur.execute("UPDATE sylvex_storage_reference_tables SET backfilled_at=NULL,backfill_cursor=NULL,recording_since=NOW()")
    return True


def trusted_reference_tables(cur, cached=None):
    """{table: pk columns} whose reference index is complete and current.

    cached: an earlier result in the same run; only the cheap check that the
    installed guard still records references is repeated (a rollback to an
    older release stops recording at once).
    """
    if cached is not None:
        return cached if cached and _guard_records_references(cur) else {}
    cur.execute("SELECT to_regclass('sylvex_storage_reference_tables')")
    if cur.fetchone()[0] is None or not _guard_records_references(cur):
        return {}
    cur.execute("SELECT table_name,pk_columns FROM sylvex_storage_reference_tables "
                "WHERE backfilled_at IS NOT NULL AND pk_columns<>''")
    trusted = {}
    for table, pk in cur.fetchall():
        if primary_key(cur, table) == pk.split(","):
            trusted[table] = pk.split(",")
    return trusted


def backfill_reference_index(database_url, *, batch=500, wait_for_older=True, wait_seconds=600, pause=0.0, max_seconds=None):
    """Resumable backfill of rows written before recording started.

    Per table: wait until no transaction that began before recording_since
    can still commit an unrecorded write, then walk the primary key in
    batches (one short transaction each, cursor saved), then mark the table
    complete. Safe to stop and re-run at any point.
    """
    import json, time
    from psycopg2.extras import execute_values
    from services.account_erasure import transaction, ident
    started, totals = time.monotonic(), {"rows": 0, "entries": 0, "tables_done": 0}
    with transaction(database_url) as cur:
        cur.execute("SELECT table_name,pk_columns,recording_since,backfill_cursor FROM sylvex_storage_reference_tables "
                    "WHERE backfilled_at IS NULL AND pk_columns<>'' ORDER BY table_name")
        pending = cur.fetchall()
    for table, pk_list, since, cursor in pending:
        pk = pk_list.split(",")
        if wait_for_older:
            deadline = time.monotonic() + wait_seconds
            while True:
                with transaction(database_url) as cur:
                    cur.execute("SELECT COUNT(*) FROM pg_stat_activity WHERE pid<>pg_backend_pid() "
                                "AND datname=current_database() AND xact_start<%s "
                                "AND (backend_xid IS NOT NULL OR state='active')", (since,))
                    if cur.fetchone()[0] == 0:
                        break
                if time.monotonic() > deadline:
                    return {**totals, "pending": [table], "blocked_by_older_transactions": True}
                time.sleep(1)
        order = ",".join("t." + ident(c) for c in pk)
        ref = "jsonb_build_array(" + ",".join("to_jsonb(t)->" + "'" + c.replace("'", "''") + "'" for c in pk) + ")::text"
        while True:
            if max_seconds is not None and time.monotonic() - started > max_seconds:
                return {**totals, "pending": [table], "stopped": "max_seconds"}
            with transaction(database_url) as cur:
                where, params = "TRUE", []
                if cursor:
                    where = "(" + order + ")>(" + ",".join(["%s"] * len(pk)) + ")"
                    params = json.loads(cursor)
                cur.execute("SELECT " + ref + ",sylvex_erasure_reference_keys(to_jsonb(t)) FROM " + ident(table) + " t WHERE " +
                            where + " ORDER BY " + order + " LIMIT %s", params + [int(batch)])
                rows = cur.fetchall()
                if not rows:
                    cur.execute("UPDATE sylvex_storage_reference_tables SET backfilled_at=NOW() WHERE table_name=%s", (table,))
                    totals["tables_done"] += 1
                    break
                entries = [(key, table, row_ref) for row_ref, keys in rows for key in (keys or [])
                           if key.startswith(REFERENCE_PREFIX) and len(key) <= REFERENCE_MAX_KEY]
                if entries:
                    execute_values(cur, "INSERT INTO sylvex_storage_references(object_key,source_table,source_row) VALUES %s "
                                   "ON CONFLICT DO NOTHING", entries, page_size=1000)
                cursor = rows[-1][0]
                cur.execute("UPDATE sylvex_storage_reference_tables SET backfill_cursor=%s WHERE table_name=%s", (cursor, table))
                totals["rows"] += len(rows); totals["entries"] += len(entries)
            if pause:
                time.sleep(pause)
    return {**totals, "pending": []}


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
