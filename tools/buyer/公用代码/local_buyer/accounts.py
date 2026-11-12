"""Buyer identity, address book and tokenized payment methods."""
import copy
import re

from local_commerce.core import moment, page, text, touch, version
from local_commerce.types import Address


class Accounts:
    def get_buyer_profile(self) -> dict:
        """读取当前买家的资料、默认地址及已绑定支付方式。"""
        with self.session() as s:
            b = self.actor(s)
            return {"buyer": {k: copy.deepcopy(b.get(k)) for k in ("id", "name", "email", "phone", "default_address_id", "default_payment_method_id", "version")},
                    "payment_methods": [self.method_view(m) for m in b["payment_methods"]]}

    def update_buyer_profile(self, name: str | None = None, email: str | None = None, phone: str | None = None, expected_version: int | None = None) -> dict:
        """更新买家的姓名、联系邮箱和电话。"""
        def apply(s, outputs):
            b = self.actor(s)
            version(b, expected_version)
            for key, value in {"name": name, "email": email, "phone": phone}.items():
                if value is not None:
                    text(value, 300)
                    if key == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
                        raise ValueError("Invalid email")
                    b[key] = value
            touch(b, s["now"])
            return {"buyer": {k: b.get(k) for k in ("id", "name", "email", "phone", "version")}}
        return self.mutate("update_buyer_profile", locals_args(locals()), apply)

    def list_addresses(self, offset: int = 0, limit: int = 20) -> dict:
        """列出当前买家的收件地址。"""
        with self.session() as s:
            return page([a for a in s["addresses"].values() if a["buyer_id"] == self.actor_id], offset, limit)

    def save_address(self, label: str, address: Address, address_id: str | None = None, make_default: bool = False, expected_version: int | None = None) -> dict:
        """新增或修改地址；已保存的报价和订单继续使用原有地址快照。"""
        def apply(s, outputs):
            text(label, 100)
            a = self.owned(s, "addresses", address_id) if address_id else {"id": self.new_id(s, "addresses", "addr"), "buyer_id": self.actor_id, "version": 0}
            version(a, expected_version)
            a.update(label=label, address=self.address_check(address))
            touch(a, s["now"])
            s["addresses"][a["id"]] = a
            b = self.actor(s)
            if make_default or not b.get("default_address_id"):
                b["default_address_id"] = a["id"]
                touch(b, s["now"])
            return {"address": a}
        return self.mutate("save_address", locals_args(locals()), apply)

    def delete_address(self, address_id: str) -> dict:
        """删除地址簿中的地址，不修改已有订单。"""
        def apply(s, outputs):
            self.owned(s, "addresses", address_id)
            del s["addresses"][address_id]
            b = self.actor(s)
            if b.get("default_address_id") == address_id:
                b["default_address_id"] = None
                touch(b, s["now"])
            return {"deleted_address_id": address_id}
        return self.mutate("delete_address", {"address_id": address_id}, apply)

    def set_default_address(self, address_id: str) -> dict:
        """设置后续购买使用的默认地址。"""
        def apply(s, outputs):
            self.owned(s, "addresses", address_id)
            b = self.actor(s)
            b["default_address_id"] = address_id
            touch(b, s["now"])
            return {"default_address_id": address_id}
        return self.mutate("set_default_address", {"address_id": address_id}, apply)

    def list_payment_methods(self) -> dict:
        """列出支付方式及默认支付方式。"""
        with self.session() as s:
            b = self.actor(s)
            return {"payment_methods": [self.method_view(m) for m in b["payment_methods"]], "default_payment_method_id": b.get("default_payment_method_id")}

    def bind_payment_method(self, payment_token: str, make_default: bool = False) -> dict:
        """使用支付服务签发的凭证绑定支付方式。"""
        def apply(s, outputs):
            token = self.get(s, "payment_tokens", payment_token)
            if token["buyer_id"] != self.actor_id or token.get("consumed") or token.get("expires_at") and moment(s["now"]) >= moment(token["expires_at"]):
                raise ValueError("Payment token is unavailable")
            m = {"id": self.new_id(s, "payment_tokens", "pm"), "label": token["label"], "outcome": token["outcome"], "active": True, "version": 1}
            b = self.actor(s)
            while any(old["id"] == m["id"] for old in b["payment_methods"]):
                m["id"] = self.new_id(s, "payment_tokens", "pm")
            b["payment_methods"].append(m)
            token["consumed"] = True
            if make_default or not b.get("default_payment_method_id"):
                b["default_payment_method_id"] = m["id"]
            touch(b, s["now"])
            return {"payment_method": self.method_view(m)}
        return self.mutate("bind_payment_method", {"token_reference": payment_token, "make_default": make_default}, apply)

    def unbind_payment_method(self, payment_method_id: str) -> dict:
        """停用绑定的支付方式；使用该方式的订阅需要另行更换。"""
        def apply(s, outputs):
            m = self.payment_method(s, self.actor_id, payment_method_id)
            m["active"] = False
            touch(m, s["now"])
            b = self.actor(s)
            if b.get("default_payment_method_id") == payment_method_id:
                b["default_payment_method_id"] = None
            return {"payment_method": self.method_view(m)}
        return self.mutate("unbind_payment_method", {"payment_method_id": payment_method_id}, apply)

    def set_default_payment_method(self, payment_method_id: str) -> dict:
        """设置默认支付方式，不改变已有订阅的扣款方式。"""
        def apply(s, outputs):
            if not self.payment_method(s, self.actor_id, payment_method_id)["active"]:
                raise ValueError("Payment method is inactive")
            self.actor(s)["default_payment_method_id"] = payment_method_id
            touch(self.actor(s), s["now"])
            return {"default_payment_method_id": payment_method_id}
        return self.mutate("set_default_payment_method", {"payment_method_id": payment_method_id}, apply)


def locals_args(values):
    return {k: copy.deepcopy(v) for k, v in values.items() if k not in {"self", "apply"}}
