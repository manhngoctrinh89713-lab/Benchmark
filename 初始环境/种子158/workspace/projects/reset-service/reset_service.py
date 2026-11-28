import secrets

_next_ticket = 10420
requests = {}

def create_request(account_id):
    global _next_ticket
    _next_ticket += 1
    ticket_id = f"RST-{_next_ticket:06d}"
    reset_token = secrets.token_urlsafe(24)
    requests[ticket_id] = {"account_id": account_id, "reset_token": reset_token}
    return {"ticket_id": ticket_id, "reset_token": reset_token}

def validate_reset(account_id, token):
    return any(record["account_id"] == account_id and secrets.compare_digest(record["reset_token"], str(token)) for record in requests.values())
