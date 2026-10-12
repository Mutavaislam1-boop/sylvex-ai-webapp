"""In-memory stand-in for the parts of the Stripe REST API that
services/stripe_billing.py uses. It receives the real form-encoded requests
StripeClient sends, so the client, the catalog sync and checkout run
unchanged. No network, no real payments."""
import hashlib
import hmac
import itertools
import json
import re
import time
from urllib.parse import urlparse


def unflatten(pairs):
    """Stripe form pairs (a[b][0][c]=v) back into nested dicts/lists."""
    root = {}
    for key, value in pairs or []:
        parts = re.findall(r"[^\[\]]+", key)
        node = root
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if last:
                node[part] = value
            else:
                node = node.setdefault(part, {})
    return _lists(root)


def _lists(node):
    if isinstance(node, dict):
        node = {k: _lists(v) for k, v in node.items()}
        if node and all(k.isdigit() for k in node):
            return [node[k] for k in sorted(node, key=int)]
    return node


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.content = json.dumps(body).encode()

    def json(self):
        return self._body


class FakeStripe:
    def __init__(self, livemode=False):
        self.livemode = livemode
        self.products = {}
        self.prices = {}
        self.sessions = {}
        self.subscriptions = {}
        self.calls = []
        self.fail_next = []  # [(method, path_prefix, status, code)]
        self._ids = itertools.count(1)

    def _new_id(self, prefix):
        return f"{prefix}_{next(self._ids):06d}"

    def _error(self, status, message, code=None):
        return Response(status, {"error": {"message": message, "code": code, "type": "invalid_request_error"}})

    # requests.Session-compatible entry point
    def request(self, method, url, params=None, data=None, headers=None, timeout=None):
        path = urlparse(url).path.replace("/v1", "", 1)
        body = unflatten(params if method == "GET" else data)
        self.calls.append((method, path, body, dict(headers or {})))
        assert (headers or {}).get("Authorization", "").startswith("Bearer sk_")
        for i, (m, prefix, status, code) in enumerate(self.fail_next):
            if m == method and path.startswith(prefix):
                self.fail_next.pop(i)
                return self._error(status, "injected failure", code)
        handler = getattr(self, "_" + method.lower() + "_" + path.strip("/").split("/")[0].replace("-", "_"), None)
        if not handler:
            return self._error(404, f"Unrecognized request URL ({method}: {path})")
        return handler(path, body)

    # products
    def _get_products(self, path, body):
        product_id = path.rsplit("/", 1)[-1]
        if product_id in self.products:
            return Response(200, self.products[product_id])
        return self._error(404, f"No such product: '{product_id}'", "resource_missing")

    def _post_products(self, path, body):
        if path.count("/") > 1:  # update
            product = self.products[path.rsplit("/", 1)[-1]]
            product.update({k: v for k, v in body.items()})
            return Response(200, product)
        if body["id"] in self.products:
            return self._error(400, "Product already exists.", "resource_already_exists")
        product = {"id": body["id"], "object": "product", "name": body["name"], "description": body.get("description"),
                   "metadata": body.get("metadata") or {}, "active": True, "livemode": self.livemode}
        self.products[product["id"]] = product
        return Response(200, product)

    # prices
    def _get_prices(self, path, body):
        keys = body.get("lookup_keys") or []
        data = [p for p in self.prices.values() if p["lookup_key"] in keys and (body.get("active") != "true" or p["active"])]
        return Response(200, {"object": "list", "data": data, "has_more": False})

    def _post_prices(self, path, body):
        key = body.get("lookup_key")
        holder = next((p for p in self.prices.values() if key and p["lookup_key"] == key), None)
        if holder and body.get("transfer_lookup_key") != "true":
            return self._error(400, "A price with this lookup key already exists.", "lookup_key_exists")
        if holder:
            holder["lookup_key"] = None
        recurring = body.get("recurring")
        price = {"id": self._new_id("price"), "object": "price", "product": body["product"], "currency": body["currency"],
                 "unit_amount": int(body["unit_amount"]), "lookup_key": key, "active": True, "nickname": body.get("nickname"),
                 "metadata": body.get("metadata") or {}, "livemode": self.livemode,
                 "recurring": {"interval": recurring["interval"], "interval_count": 1} if recurring else None,
                 "type": "recurring" if recurring else "one_time"}
        self.prices[price["id"]] = price
        return Response(200, price)

    # checkout
    def _post_checkout(self, path, body):
        for item in body.get("line_items") or []:
            if "price" in item:
                price = self.prices.get(item["price"])
                if not price or not price["active"]:
                    return self._error(400, f"No such price: '{item['price']}'", "resource_missing")
        if body.get("customer") and body["customer"].startswith("cus_deleted"):
            return self._error(400, "No such customer", "resource_missing")
        session = {"id": self._new_id("cs_test"), "object": "checkout.session", "url": "https://checkout.stripe.com/c/pay/x",
                   "params": body}
        self.sessions[session["id"]] = session
        return Response(200, session)

    # subscriptions
    def _get_subscriptions(self, path, body):
        sub_id = path.rsplit("/", 1)[-1]
        if sub_id in self.subscriptions:
            return Response(200, self.subscriptions[sub_id])
        return self._error(404, "No such subscription", "resource_missing")

    def _post_test_helpers(self, path, body):
        clock = {"id": self._new_id("clock"), "object": "test_helpers.test_clock", "frozen_time": int(body["frozen_time"]),
                 "name": body.get("name"), "livemode": False}
        self.test_clocks = getattr(self, "test_clocks", {})
        self.test_clocks[clock["id"]] = clock
        return Response(200, clock)

    def _post_customers(self, path, body):
        customer = {"id": self._new_id("cus"), "object": "customer", "test_clock": body.get("test_clock"),
                    "metadata": body.get("metadata") or {}, "livemode": self.livemode}
        self.customers = getattr(self, "customers", {})
        self.customers[customer["id"]] = customer
        return Response(200, customer)

    def _post_billing_portal(self, path, body):
        return Response(200, {"id": self._new_id("bps"), "url": "https://billing.stripe.com/p/session/x", "customer": body["customer"],
                              "return_url": body.get("return_url")})


def sign(payload: bytes, secret: str, timestamp=None):
    timestamp = int(timestamp if timestamp is not None else time.time())
    signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def event(event_type, obj, event_id=None, livemode=False):
    return {"id": event_id or f"evt_{event_type}_{obj.get('id')}", "object": "event", "type": event_type,
            "livemode": livemode, "data": {"object": obj}}
