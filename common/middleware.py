"""Middleware that resolves the tenant from the ``X-Company-ID`` header.

``request.company`` is set to the ``Company`` instance only when:

1. The header is present.
2. The user is authenticated.
3. The header value matches the user's own ``company_id``.

Otherwise ``request.company`` is ``None`` — never guessed, never defaulted.
"""


class CompanyContextMiddleware:
    """Reads ``X-Company-ID`` from the request header and validates it matches
    the authenticated user's own company before trusting it.

    ``request.company`` is ``None`` for unauthenticated requests or a
    mismatched/missing header — never guessed, never defaulted.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.company = None
        company_id = request.headers.get("X-Company-ID")
        user = getattr(request, "user", None)
        if company_id and user and user.is_authenticated:
            if str(user.company_id) == str(company_id):
                request.company = user.company
        return self.get_response(request)
