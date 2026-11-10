"""`requests`, imported on first use.

Importing requests (and urllib3) costs ~0.1 s, and only background downloads need
it, so modules take it from here instead of importing it at startup.
"""


class _LazyRequests:
    def __getattr__(self, name):
        import requests
        return getattr(requests, name)


requests = _LazyRequests()
