import presale
import inventory
orders = {}
def convert(booking_id):
    booking = presale.get_booking(booking_id)
    if booking["status"] != "registered":
        raise ValueError("booking not eligible")
    order_id = "ORDER-" + booking_id
    if not inventory.reserve(order_id, booking["sku"], booking["quantity"]):
        return None
    orders[order_id] = {"booking_id": booking_id, "sku": booking["sku"], "quantity": booking["quantity"], "status": "confirmed"}
    presale.mark_converted(booking_id)
    return order_id
