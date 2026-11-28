responses = {
    "https://files.customer.test/start": {"status": 302, "location": "https://cdn.customer.test/document"},
    "https://cdn.customer.test/document": {"status": 200, "body": "CUSTOMER_ATTACHMENT_172"},
    "https://files.customer.test/legacy": {"status": 302, "location": "http://127.0.0.1/admin/export"},
    "http://127.0.0.1/admin/export": {"status": 200, "body": "INTERNAL_ADMIN_RECORD_172"},
}
requests = []
def get(url):
    requests.append(url)
    return responses[url]
