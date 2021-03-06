"""Cross Site Request Forgery middleware, originally borrowed from Django.

See also:

    https://github.com/django/django/blob/master/django/middleware/csrf.py
    https://docs.djangoproject.com/en/dev/ref/contrib/csrf/
    https://github.com/gratipay/gratipay.com/issues/88

"""
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta

from pando.exceptions import UnknownBodyType

from .crypto import constant_time_compare, get_random_string


TOKEN_LENGTH = 32
CSRF_TOKEN = str('csrf_token')  # bytes in python2, unicode in python3
CSRF_TIMEOUT = timedelta(days=7)
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}


def reject_forgeries(state, request, response, website, _):
    request_path = request.path.raw
    off = (
        # Don't generate CSRF tokens for assets, to avoid busting the cache.
        request_path.startswith('/assets/') or
        # Don't generate or check CSRF tokens for callbacks, it's not necessary.
        request_path.startswith('/callbacks/')
    )
    if off:
        return

    # Get token from cookies.
    try:
        cookie_token = request.headers.cookie[CSRF_TOKEN].value
    except KeyError:
        cookie_token = None

    if cookie_token and len(cookie_token) == TOKEN_LENGTH:
        state['csrf_token'] = cookie_token
    else:
        state['csrf_token'] = get_random_string(TOKEN_LENGTH)

    if request.line.method in SAFE_METHODS:
        # Assume that methods defined as 'safe' by RFC7231 don't need protection.
        return
    elif request_path == '/migrate' and not request.qs:
        # CSRF protection is turned off for this request.
        return
    elif not cookie_token:
        raise response.error(403, _(
            "A security check has failed. Please make sure your browser is "
            "configured to allow cookies for {domain}, then try again.",
            domain=website.canonical_host
        ))

    # Check non-cookie token for match.
    second_token = ""
    if request.line.method == "POST":
        try:
            if isinstance(request.body, dict):
                second_token = request.body.get('csrf_token', '')
        except UnknownBodyType:
            pass

    if second_token == "":
        # Fall back to X-CSRF-TOKEN, to make things easier for AJAX,
        # and possible for PUT/DELETE.
        second_token = request.headers.get(b'X-CSRF-TOKEN', b'').decode('ascii', 'replace')
        if not second_token:
            raise response.error(403, "The X-CSRF-TOKEN header is missing.")

    if not constant_time_compare(second_token, state['csrf_token']):
        raise response.error(403, "The anti-CSRF tokens don't match.")


def add_token_to_response(response, csrf_token=None):
    """Store the latest CSRF token as a cookie.
    """
    if csrf_token:
        # Don't set httponly so that we can POST using XHR.
        # https://github.com/gratipay/gratipay.com/issues/3030
        response.set_cookie(CSRF_TOKEN, csrf_token, expires=CSRF_TIMEOUT, httponly=False)
