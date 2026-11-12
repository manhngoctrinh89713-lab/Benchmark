"""Public shared commerce store and backward-compatible primitive imports."""
from .common import integer, moment, page, period_end, text, touch, version
from .engine import Engine
from .store import Storage
from .fulfillment import Fulfillment


class CommerceStore(Engine, Fulfillment, Storage):
    """Role-bound operations share one inventory, contract and money ledger."""
