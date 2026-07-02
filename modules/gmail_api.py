import base64
import os

import requests

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def _client_config(client_id, client_secret, redirect_uri):
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": [redirect_uri],
        }
    }


def build_gmail_oauth_url(client_id, client_secret, redirect_uri, state, login_hint=""):
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:  # pragma: no cover - dependency error is surfaced in UI
        raise RuntimeError("google-auth-oauthlib is not installed.") from exc

    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    flow = Flow.from_client_config(
        _client_config(client_id, client_secret, redirect_uri),
        scopes=[GMAIL_SEND_SCOPE],
        state=state,
    )
    flow.redirect_uri = redirect_uri
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        login_hint=login_hint or None,
    )
    return authorization_url


def exchange_gmail_oauth_code(client_id, client_secret, redirect_uri, authorization_response, state):
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("google-auth-oauthlib is not installed.") from exc

    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    flow = Flow.from_client_config(
        _client_config(client_id, client_secret, redirect_uri),
        scopes=[GMAIL_SEND_SCOPE],
        state=state,
    )
    flow.redirect_uri = redirect_uri
    flow.fetch_token(authorization_response=authorization_response)
    return flow.credentials


def refresh_gmail_access_token(client_id, client_secret, refresh_token):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("google-auth is not installed.") from exc

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=[GMAIL_SEND_SCOPE],
    )
    credentials.refresh(Request())
    return credentials.token


def send_gmail_api_message(client_id, client_secret, refresh_token, message_bytes):
    access_token = refresh_gmail_access_token(client_id, client_secret, refresh_token)
    encoded_message = base64.urlsafe_b64encode(message_bytes).decode("ascii")
    response = requests.post(
        GMAIL_SEND_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={"raw": encoded_message},
        timeout=30,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"error": response.text}
    if not response.ok:
        message = payload.get("error") if isinstance(payload.get("error"), str) else payload
        raise RuntimeError(f"Gmail API send failed: {message}")
    return payload
