import transport
import policy
def download(url):
    for step in range(8):
        if not policy.allowed(url):
            raise PermissionError("destination not authorized")
        response = transport.get(url)
        if response["status"] == 200:
            return response["body"]
        url = response["location"]
    raise ValueError("too many redirects")
