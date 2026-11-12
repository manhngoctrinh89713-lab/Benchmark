import hashlib
import hmac
import json

_TEST_SECRET = b"local-sdk-key"

def verify_notice(raw_body, signature):
    """Verify the signature of the original UTF-8 request body; return bool."""
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    expected = hmac.new(_TEST_SECRET, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")

def check_notice(notice):
    """Legacy payment-notice adapter; retained during SDK transition."""
    payload = {key: value for key, value in notice.items() if key != "signature"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return (verify_notice(raw, notice.get("signature"))
            and notice.get("event_type") == "payment.succeeded")
