"""Owner-operated review/refund commands. No public HTTP endpoint.

Every balance correction or real Stars refund needs separate per-payment
owner authorization. Commands require --confirm; tests use fakes only.
"""
import argparse
import json
import os
import urllib.request

if __package__=='services':
    from services import payment_reviews as reviews,billing_safety as wallet
else:
    from app.database import payment_reviews as reviews,credit_wallet as wallet


def connect():
    import psycopg2
    url=os.getenv('DATABASE_URL')or os.getenv('DATABASE_PUBLIC_URL')
    if not url:raise reviews.ReviewError('database_configuration_required')
    return psycopg2.connect(url)


def stars_provider_call(user_id,charge_id):
    token=os.getenv('BOT_TOKEN','').strip()
    if not token:raise reviews.ReviewError('bot_configuration_required')
    body=json.dumps({'user_id':user_id,'telegram_payment_charge_id':charge_id}).encode()
    request=urllib.request.Request('https://api.telegram.org/bot'+token+'/refundStarPayment',data=body,headers={'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=30)as response:
        value=json.load(response)
        return response.status==200 and value.get('ok')is True and value.get('result')is True


def _mode(case_id,expected):
    with reviews.transaction(connect)as conn:
        with conn.cursor()as cur:
            cur.execute('SELECT provider,livemode FROM financial_review_cases WHERE case_id=%s',(case_id,));row=cur.fetchone()
            if not row:raise reviews.ReviewError('case_not_found')
            actual='stars'if row[0]=='telegram_stars'else'stripe-live'if row[1]else'stripe-test'
            if actual!=expected:raise reviews.ReviewError('payment_mode_mismatch')


def main(argv=None):
    parser=argparse.ArgumentParser(description='SYLVEX verified payment review; no automatic credit clawbacks')
    commands=parser.add_subparsers(dest='command',required=True)
    show=commands.add_parser('list');show.add_argument('--limit',type=int,default=50)
    preview=commands.add_parser('preview-wallet');preview.add_argument('--case-id',required=True)
    resolve=commands.add_parser('resolve')
    resolve.add_argument('--case-id',required=True);resolve.add_argument('--revision',required=True,type=int)
    resolve.add_argument('--decision',required=True,choices=sorted(reviews.DECISIONS))
    resolve.add_argument('--credits',type=int,default=0);resolve.add_argument('--source',choices=['purchased','subscription'])
    resolve.add_argument('--confirmed-unspent-credits',type=int)
    for field in ['balance','purchased','subscription']:resolve.add_argument('--expected-'+field,type=int)
    mapping=commands.add_parser('map-original');mapping.add_argument('--case-id',required=True)
    mapping.add_argument('--purchase-id',required=True,type=int);mapping.add_argument('--revision',required=True,type=int)
    mapping.add_argument('--source',choices=['purchased','subscription'])
    refund=commands.add_parser('refund-stars');refund.add_argument('--purchase-id',type=int,required=True)
    refund.add_argument('--confirm-stars-real',action='store_true')
    reconciliation=commands.add_parser('reconcile-stars-request');reconciliation.add_argument('--request-id',required=True)
    reconciliation.add_argument('--result',choices=['refunded','not-refunded'],required=True)
    for cmd in [resolve,mapping]:cmd.add_argument('--mode',choices=['stripe-test','stripe-live','stars'],required=True)
    for cmd in [resolve,mapping,refund,reconciliation]:
        cmd.add_argument('--operator',required=True);cmd.add_argument('--evidence',required=True);cmd.add_argument('--confirm',action='store_true')
    args=parser.parse_args(argv)
    if args.command not in('list','preview-wallet')and not args.confirm:parser.error('separate owner authorization and --confirm are required')
    if args.command=='refund-stars'and not args.confirm_stars_real:parser.error('Stars are real payments: --confirm-stars-real is required')
    try:
        if args.command=='list':
            result={'summary':reviews.summary(connect),'cases':reviews.pending_cases(connect,args.limit)}
            with reviews.transaction(connect)as conn:
                with conn.cursor()as cur:
                    cur.execute("SELECT request_id,purchase_id,status FROM payment_refund_requests WHERE status IN('dispatching','pending_reconciliation')ORDER BY created_at LIMIT %s",(min(200,max(1,args.limit)),))
                    result['refund_requests']=[dict(request_id=a,purchase_id=b,status=c)for a,b,c in cur.fetchall()]
                    cur.execute("SELECT provider,livemode,event_id,event_type,attempts,last_error_class,received_at,next_attempt_at FROM financial_review_events WHERE status='pending'ORDER BY received_at LIMIT %s",(min(200,max(1,args.limit)),))
                    result['pending_events']=[dict(zip(['provider','livemode','event_id','event_type','attempts','last_error_class','received_at','next_attempt_at'],row))for row in cur.fetchall()]
        elif args.command=='preview-wallet':
            with reviews.transaction(connect)as conn:
                with conn.cursor()as cur:
                    cur.execute('''SELECT c.telegram_id,u.balance,w.purchased_credits,w.subscription_credits,w.subscription_expires_at
                        FROM financial_review_cases c LEFT JOIN users u ON u.telegram_id=c.telegram_id
                        LEFT JOIN user_credit_wallets w ON w.telegram_id=c.telegram_id WHERE c.case_id=%s''',(args.case_id,));row=cur.fetchone()
                    if not row:raise reviews.ReviewError('case_not_found')
                    result=dict(zip(['telegram_id','balance','purchased','subscription','subscription_expires_at'],row))
                    result['read_only_snapshot']=True
        elif args.command=='resolve':
            _mode(args.case_id,args.mode)
            result=reviews.resolve(connect,args.case_id,args.revision,operator=args.operator,evidence=args.evidence,
                decision=args.decision,credits=args.credits,source=args.source,expected_balance=args.expected_balance,
                expected_purchased=args.expected_purchased,expected_subscription=args.expected_subscription,
                confirmed_unspent_credits=args.confirmed_unspent_credits,wallet=wallet)
        elif args.command=='map-original':
            _mode(args.case_id,args.mode)
            result=reviews.map_original(connect,args.case_id,args.purchase_id,args.revision,operator=args.operator,
                                        evidence=args.evidence,source=args.source)
        elif args.command=='refund-stars':
            result=reviews.request_stars_refund(connect,args.purchase_id,stars_provider_call,operator=args.operator,evidence=args.evidence)
        else:
            result=reviews.resolve_stars_request(connect,args.request_id,refunded=args.result=='refunded',operator=args.operator,evidence=args.evidence)
        print(json.dumps(result,default=str));return 0
    except Exception as error:
        # No provider URLs, payloads, credentials or raw HTTP errors.
        print(json.dumps({'operation_failed':True,'error_class':type(error).__name__,
                          'reason':str(error)if isinstance(error,reviews.ReviewError)else'provider_or_database_error'}));return 1


if __name__=='__main__':raise SystemExit(main())
