"""Cookie-based operator identity — the seam described in docs/08a §1.3.

Locally this is a signed cookie holding a chosen name; it replaces
`getpass.getuser()` so every audit-trail `actor` value comes from a real
per-request source instead of the server process's OS account. When the app
moves to the KLK network, only this module's `read_actor`/`sign_actor` need
to change (to AD/SSO) — routers already call `current_actor(request)`, never
the cookie or `getpass` directly.
"""

import itsdangerous
from fastapi import Request

# Local single-user/small-team deployment only. Rotate and move to an env
# var before this app is ever exposed beyond the KLK network.
SECRET_KEY = "eudr-dashboard-local-dev-secret-2026"
COOKIE_NAME = "eudr_actor"
MAX_AGE = 60 * 60 * 24 * 30  # 30 days

_signer = itsdangerous.URLSafeTimedSerializer(SECRET_KEY, salt="eudr-actor-session")


def sign_actor(name: str) -> str:
    return _signer.dumps(name)


def read_actor(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return _signer.loads(token, max_age=MAX_AGE)
    except itsdangerous.BadData:
        return None


class NotAuthenticated(Exception):
    """Raised by current_actor() when no valid session cookie is present."""
