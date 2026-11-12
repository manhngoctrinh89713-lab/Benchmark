from local_buyer.catalog import register_tool


def register(server, store):
    register_tool(server, store, 'checkout_cart')
