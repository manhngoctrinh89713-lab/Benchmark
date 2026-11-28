def check_non_negative(rows):
    return [r for r in rows if r.get('amount', 0) >= 0]
