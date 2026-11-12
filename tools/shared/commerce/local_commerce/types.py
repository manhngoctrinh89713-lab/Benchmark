"""Finite structured commerce arguments."""
from typing import Literal
from typing_extensions import TypedDict, Required
from pydantic import ConfigDict


class Address(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    address_line_1: Required[str]
    country_code: Required[str]
    address_line_2: str
    admin_area_1: str
    admin_area_2: str
    postal_code: str
    recipient: str
    phone: str


class CartLine(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    product_id: str
    sku_id: str
    quantity: Required[int]


class OrderLineQuantity(TypedDict):
    __pydantic_config__ = ConfigDict(extra="forbid")
    line_id: str
    quantity: int


class SalePolicy(TypedDict, total=False):
    __pydantic_config__ = ConfigDict(extra="forbid")
    terms: str
    returnable: bool
    exchangeable: bool
    return_days: int
    cancellation_allowed: bool
    delivery_countries: list[str]
