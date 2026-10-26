"""Retired PayPal routes reject both old checkouts and webhooks without side effects.
Stripe is covered separately by test_stripe_billing.py. No external services are used.
"""
import asyncio
import json
import os

import pytest
import main

HANDLERS = [main.public_paypal_create_order, main.public_paypal_subscription_binding,
            main.public_paypal_subscription_created, main.public_paypal_webhook]


class UnreadableRequest:
    async def json(self):
        raise AssertionError('Retired provider must not parse checkout data')
    async def body(self):
        raise AssertionError('Retired provider must not parse a webhook')


@pytest.fixture(autouse=True)
def no_paypal_side_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Retired PayPal attempted external access or a write')
    for name in ('create_paypal_order', 'save_paypal_order', 'save_paypal_subscription',
                 'verified_paypal_subscription', 'verify_paypal_webhook',
                 'activate_paypal_subscription_from_event', 'sync_paypal_subscription_lifecycle_event',
                 'finalize_paypal_capture', 'finalize_shop_payment', 'log_user_event',
                 'make_binding', 'read_binding'):
        monkeypatch.setattr(main, name, forbidden)
    monkeypatch.setattr(main.requests, 'post', forbidden)
    monkeypatch.setattr(main.requests, 'get', forbidden)
    monkeypatch.setattr(main, 'db_connect', forbidden)


@pytest.mark.parametrize('configured', [False, True])
@pytest.mark.parametrize('handler', HANDLERS)
def test_retired_routes_return_410_before_parsing_or_side_effects(monkeypatch, handler, configured):
    for name in ('PAYPAL_CLIENT_ID', 'PAYPAL_CLIENT_SECRET', 'PAYPAL_WEBHOOK_ID',
                 'PAYPAL_PRO_MONTHLY_PLAN_ID', 'PAYPAL_PRO_YEARLY_PLAN_ID'):
        monkeypatch.setattr(main, name, 'dummy-present' if configured else '')
    response = asyncio.run(handler(UnreadableRequest()))
    assert response.status_code == 410
    assert json.loads(response.body) == {'ok': False, 'error': 'paypal_retired'}


@pytest.mark.parametrize('stripe_on', [False, True])
def test_public_config_disables_paypal_without_changing_stripe(monkeypatch, stripe_on):
    monkeypatch.setattr(main, 'stripe_enabled', lambda: stripe_on)
    monkeypatch.setattr(main, 'PAYPAL_CLIENT_ID', 'dummy-client-id')
    monkeypatch.setattr(main, 'PAYPAL_CLIENT_SECRET', 'dummy-secret-never-published')
    monkeypatch.setattr(main, 'PAYPAL_PRO_MONTHLY_PLAN_ID', 'P-DUMMYMONTH')
    monkeypatch.setattr(main, 'PAYPAL_PRO_YEARLY_PLAN_ID', 'P-DUMMYYEAR')
    config = asyncio.run(main.public_config())
    assert config['stripe_enabled'] is stripe_on
    assert config['paypal_enabled'] is False and config['paypal_subscriptions_enabled'] is False
    assert config['paypal_client_id'] == config['paypal_pro_monthly_plan_id'] == config['paypal_pro_yearly_plan_id'] == ''
    assert 'dummy-secret-never-published' not in json.dumps(config)
    assert main.paypal_configured() is False
    assert main.paypal_subscriptions_configured() is False


def test_old_catalog_has_no_payment_links_or_products():
    response = asyncio.run(main.payment_links())
    assert response == {'success': True, 'source': 'retired', 'products': [], 'packages': {}}


def test_old_helpers_cannot_authenticate_even_with_leftover_variables(monkeypatch):
    monkeypatch.setattr(main, 'PAYPAL_CLIENT_ID', 'dummy-id')
    monkeypatch.setattr(main, 'PAYPAL_CLIENT_SECRET', 'dummy-secret')
    with pytest.raises(RuntimeError, match='not configured'):
        main.paypal_access_token()


def test_retired_webhook_rejects_http_before_body_or_provider_access():
    import httpx
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url='https://api.example.test') as client:
            return await client.post('/api/public/payments/paypal/webhook', content=b'not-json')
    response = asyncio.run(request())
    assert response.status_code == 410
    assert response.json() == {'ok': False, 'error': 'paypal_retired'}


@pytest.mark.parametrize('event_type', ['PAYMENT.CAPTURE.COMPLETED', 'PAYMENT.SALE.COMPLETED',
    'BILLING.SUBSCRIPTION.ACTIVATED', 'BILLING.SUBSCRIPTION.CANCELLED',
    'BILLING.SUBSCRIPTION.SUSPENDED', 'BILLING.SUBSCRIPTION.EXPIRED'])
def test_webhook_does_not_acknowledge_or_apply_retired_financial_events(event_type):
    class Request:
        async def body(self):
            return json.dumps({'event_type': event_type, 'resource': {'id': 'DUMMY'}}).encode()
    response = asyncio.run(main.public_paypal_webhook(Request()))
    assert response.status_code == 410
    assert json.loads(response.body)['error'] == 'paypal_retired'


def test_retired_endpoints_preserve_historical_payment_and_subscription_rows():
    database = os.getenv('SYLVEX_TEST_DATABASE_URL')
    if not database:
        pytest.skip('Requires an isolated disposable PostgreSQL database')
    import psycopg2
    # All writes below are test fixtures in the isolated database, never production.
    with psycopg2.connect(database) as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE TEMP TABLE paypal_orders (id TEXT, amount INTEGER)')
            cur.execute('CREATE TEMP TABLE paypal_subscriptions (id TEXT, status TEXT)')
            cur.execute('CREATE TEMP TABLE payments (provider TEXT, amount INTEGER)')
            cur.execute('CREATE TEMP TABLE users (id INTEGER, balance INTEGER, subscription TEXT)')
            cur.execute("INSERT INTO paypal_orders VALUES ('DUMMY-ORDER', 500)")
            cur.execute("INSERT INTO paypal_subscriptions VALUES ('DUMMY-SUB', 'active')")
            cur.execute("INSERT INTO payments VALUES ('paypal', 500)")
            cur.execute("INSERT INTO users VALUES (101, 500, 'pro')")
            tables = ('paypal_orders', 'paypal_subscriptions', 'payments', 'users')
            def snapshot():
                rows = {}
                for table in tables:
                    cur.execute('SELECT * FROM ' + table)
                    rows[table] = cur.fetchall()
                return rows
            before = snapshot()
            for handler in HANDLERS:
                assert asyncio.run(handler(UnreadableRequest())).status_code == 410
            assert snapshot() == before


def test_lemonsqueezy_checkout_remains_discontinued():
    response = asyncio.run(main.public_lemonsqueezy_checkout(UnreadableRequest()))
    assert response.status_code == 410
