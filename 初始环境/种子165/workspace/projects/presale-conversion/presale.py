bookings = {
    "PS-A": {"sku": "P165", "quantity": 1, "status": "registered"},
    "PS-B": {"sku": "P165", "quantity": 1, "status": "registered"},
}
campaign_slots = {"maximum": 10, "registered": 2}
def get_booking(booking_id):
    return bookings[booking_id]
def mark_converted(booking_id):
    bookings[booking_id]["status"] = "converted"
