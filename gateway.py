"""Razorpay payment links (standard library only): create a link for an invoice, then check whether it was paid.

BillSaathi runs on the shop computer and cannot receive webhooks, so it asks Razorpay for the status when the owner presses
"Check payment". Needs the owner's own Razorpay account and API keys (test keys start rzp_test_, live keys rzp_live_).
The key secret is only ever sent in the HTTP Authorization header and never appears in an error message.
"""
import base64
import json
import re
import urllib.error
import urllib.request
from decimal import Decimal

BASE = "https://api.razorpay.com/v1"


class GatewayError(Exception):
    """A problem the owner can understand and act on."""


def _request(method, path, key_id, key_secret, payload=None, base=None, timeout=30):
    if not key_id or not key_secret:
        raise GatewayError("Add your Razorpay key id and secret on the Integrations page first.")
    token = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request((base or BASE) + path, data=data, method=method,
                                 headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("error", {}).get("description", "")
        except Exception:
            detail = ""
        if exc.code == 401:
            raise GatewayError("Razorpay rejected the key id or secret. Check them on the Integrations page.")
        if exc.code == 429:
            raise GatewayError("Razorpay is rate-limiting requests. Try again in a minute.")
        raise GatewayError(f"Razorpay returned an error ({exc.code}): {detail[:200]}" if detail else f"Razorpay returned an error ({exc.code}).")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise GatewayError("Cannot reach Razorpay. Check the internet connection.")
    except ValueError:
        raise GatewayError("Razorpay returned something unreadable.")


def create_link(key_id, key_secret, amount, reference, description, customer_name="", customer_phone="", base=None):
    """amount in rupees (Decimal). Returns {'id', 'short_url', 'status', 'amount'}; amount is in rupees."""
    paise = int((Decimal(amount) * 100).to_integral_value())
    if paise < 100:
        raise GatewayError("Razorpay payment links need at least ₹1.")
    body = {"amount": paise, "currency": "INR", "accept_partial": False,
            "reference_id": re.sub(r"[^A-Za-z0-9_-]", "-", reference)[:40], "description": description[:255],
            "notify": {"sms": False, "email": False}, "reminder_enable": False}
    phone = "".join(c for c in customer_phone if c.isdigit())
    if customer_name or phone:
        body["customer"] = {"name": customer_name[:100]}
        if phone:
            body["customer"]["contact"] = "+" + (phone if len(phone) > 10 else "91" + phone)
    r = _request("POST", "/payment_links", key_id, key_secret, body, base)
    if not r.get("id") or not r.get("short_url"):
        raise GatewayError("Razorpay did not return a payment link.")
    return {"id": r["id"], "short_url": r["short_url"], "status": r.get("status", "created"), "amount": Decimal(paise) / 100}


def test_keys(key_id, key_secret, base=None):
    """A harmless authenticated call (list one link) to confirm the keys work."""
    _request("GET", "/payment_links?count=1", key_id, key_secret, None, base)


def get_link(key_id, key_secret, link_id, base=None):
    """Returns {'status', 'amount', 'amount_paid'} with amounts in rupees. status: created, partially_paid, paid, cancelled, expired."""
    if not re.fullmatch(r"plink_[A-Za-z0-9]+", link_id or ""):
        raise GatewayError("That is not a Razorpay payment link id.")
    r = _request("GET", f"/payment_links/{link_id}", key_id, key_secret, None, base)
    return {"status": r.get("status", "unknown"), "amount": Decimal(r.get("amount", 0)) / 100,
            "amount_paid": Decimal(r.get("amount_paid", 0)) / 100}
