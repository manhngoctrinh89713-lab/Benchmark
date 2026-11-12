# Adapted from paypal/agent-toolkit, Apache-2.0.
# Caller supplies Decimal amounts; no remote request is performed.
import logging


def build_order_payload(params: dict) -> dict:
    try:
        curr_code = params['currency_code']
        items_in = params.get('items', [])
        shipping_cost = params.get('shipping_cost', 0)
        discount = params.get('discount', 0)
        sub_total = sum((item['item_cost'] * item.get('quantity', 1) for item in items_in))
        tax_amount = sum((item['item_cost'] * item.get('tax_percent', 0) * item.get('quantity', 1) / 100 for item in items_in))
        total = sub_total + tax_amount + shipping_cost - discount
        amount_breakdown = {'item_total': {'value': f'{sub_total:.2f}', 'currency_code': curr_code}, 'shipping': {'value': f'{shipping_cost:.2f}', 'currency_code': curr_code}, 'tax_total': {'value': f'{tax_amount:.2f}', 'currency_code': curr_code}, 'discount': {'value': f'{discount:.2f}', 'currency_code': curr_code}}
        items = []
        for item in items_in:
            items.append({'name': item['name'], 'description': item.get('description', ''), 'unit_amount': {'value': f"{item['item_cost']:.2f}", 'currency_code': curr_code}, 'quantity': str(item.get('quantity', 1)), 'tax': {'value': f"{item['item_cost'] * item.get('tax_percent', 0) / 100:.2f}", 'currency_code': curr_code}})
        base_purchase_unit = {'amount': {'value': f'{total:.2f}', 'currency_code': curr_code, 'breakdown': amount_breakdown}, 'items': items}
        if params.get('shipping_address'):
            base_purchase_unit['shipping'] = {'address': params['shipping_address']}
        request = {'intent': 'CAPTURE', 'purchase_units': [base_purchase_unit]}
        experience_context = {}
        if params.get('return_url'):
            experience_context['return_url'] = str(params['return_url'])
        if params.get('cancel_url'):
            experience_context['cancel_url'] = str(params['cancel_url'])
        if experience_context:
            request['payment_source'] = {'paypal': {'experience_context': experience_context}}
        return request
    except Exception as e:
        logging.error('parse_order_details error:', e)
        raise ValueError('Failed to parse order details') from e
