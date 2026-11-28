available = {"P165": 1}
holds = {}
def reserve(order_id, sku, quantity):
    if available[sku] < quantity:
        return False
    available[sku] -= quantity
    holds[order_id] = {"sku": sku, "quantity": quantity}
    return True
