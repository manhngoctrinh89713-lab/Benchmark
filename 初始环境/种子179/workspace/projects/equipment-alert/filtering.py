import notifier
seen_events = set()
def handle(event):
    if event["id"] in seen_events:
        return False
    seen_events.add(event["id"])
    notifier.send(event)
    return True
