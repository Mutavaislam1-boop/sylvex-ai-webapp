"""Controlled operator entrypoint. Content/file erasure requires --apply; planning records manifest metadata."""
import argparse
import json
import os

from services import account_erasure as core
from services import account_erasure_guards as guards
from services import account_erasure_restore as restore
from services import account_erasure_runner as runner


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('init','status','process','restore','reference-index'))
    parser.add_argument('--batch',type=int,default=500,help='reference-index backfill rows per transaction')
    parser.add_argument('--pause',type=float,default=0.05,help='reference-index backfill pause between batches (s)')
    parser.add_argument('--max-seconds',type=float,default=None)
    parser.add_argument('--request-id')
    parser.add_argument('--batch-size',type=int,default=50)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    database_url=os.getenv('DATABASE_URL') or os.getenv('DATABASE_PUBLIC_URL')
    if not database_url:
        print(json.dumps({'ok':False,'error':'erasure_database_unavailable'}))
        return 2
    try:
        journal=core.Journal()
        if args.command=='init':
            if not args.apply:
                result={'ok':True,'applied':False,'action':'install_schema_and_write_fences'}
            else:
                with core.transaction(database_url) as cur:
                    cur.execute("SET LOCAL lock_timeout='5s'")
                    core.ensure_schema(cur)
                    installed=guards.install(cur)
                    guards.require_installed(cur,verify_coverage=True)
                result={'ok':True,'applied':True,'guarded_tables':len(installed)}
        elif args.command=='reference-index':
            # Migration (owner approval): without --apply only reports state.
            with core.transaction(database_url) as cur:
                cur.execute("SELECT to_regclass('sylvex_storage_reference_tables')")
                installed=cur.fetchone()[0] is not None
            if args.apply:
                if not installed:
                    with core.transaction(database_url) as cur:
                        guards.install_reference_index(cur)
                result=guards.backfill_reference_index(database_url,batch=args.batch,pause=args.pause,max_seconds=args.max_seconds)
            else:
                result={'installed':installed,'applied':False}
            if installed or args.apply:
                with core.transaction(database_url) as cur:
                    cur.execute("SELECT COUNT(*),COUNT(backfilled_at),COUNT(*) FILTER (WHERE pk_columns='') "
                                "FROM sylvex_storage_reference_tables")
                    total,done,no_pk=cur.fetchone()
                    trusted=guards.trusted_reference_tables(cur)
                result.update(tables=total,backfilled=done,without_primary_key=no_pk,trusted=len(trusted))
        elif args.command=='status':
            result=restore.readiness(database_url,journal=journal)
        elif args.command=='restore':
            result=restore.replay(database_url,journal=journal,apply=args.apply,batch_size=args.batch_size)
        else:
            if not args.request_id:
                parser.error('process requires --request-id')
            result=runner.process_request(database_url,args.request_id,journal=journal,apply=args.apply,batch_size=args.batch_size)
        # No media keys, credentials, email or creative content in output.
        print(json.dumps(result,default=str,sort_keys=True))
        return 0 if not result.get('holds') and not result.get('hold_code') and not result.get('pending') else 3
    except Exception as exc:
        code=exc.code if isinstance(exc,core.ErasureError) else type(exc).__name__
        print(json.dumps({'ok':False,'error':code}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
