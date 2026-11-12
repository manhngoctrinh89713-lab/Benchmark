from local_merchant.catalog import register_tool


def register(server, store):
    register_tool(server, store, 'list_discounts')
