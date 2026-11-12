"""Buyer operations bound to one authenticated commerce account."""
from local_commerce.core import CommerceStore
from .accounts import Accounts
from .shopping import Shopping
from .orders import Orders
from .billing import Billing


class BuyerStore(Accounts, Shopping, Orders, Billing, CommerceStore):
    role = "buyer"

    def __init__(self, run_root, buyer_id=None):
        super().__init__(run_root, buyer_id)
