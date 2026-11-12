from local_buyer.catalog import register_tool


def register(server, store):
    register_tool(server, store, 'place_order_from_quote')
