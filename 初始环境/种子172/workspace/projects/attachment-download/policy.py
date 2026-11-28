def allowed(url):
    return url.startswith("https://files.customer.test/") or url.startswith("https://cdn.customer.test/")
