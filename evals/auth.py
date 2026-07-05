"""
Identity-token auth for calling a private Cloud Run backend.
Mirrors ui/app.py's get_auth_headers so evals work against BACKEND_URL
without running the FastAPI app locally.
"""

import subprocess
import logfire


def get_auth_headers(url: str) -> dict:
    """
    Returns request headers, adding a Cloud Run OIDC identity token when the
    target is a run.app URL. Tries google-auth (works for service accounts /
    metadata server), then falls back to the gcloud CLI (local user accounts).
    """
    headers = {"Content-Type": "application/json"}
    if "run.app" not in url:
        return headers

    try:
        import google.auth.transport.requests
        import google.oauth2.id_token

        audience = url.split("/query")[0]
        token = google.oauth2.id_token.fetch_id_token(
            google.auth.transport.requests.Request(), audience
        )
        headers["Authorization"] = f"Bearer {token}"
    except Exception:
        try:
            token = subprocess.check_output(
                ["gcloud", "auth", "print-identity-token"], text=True
            ).strip()
            headers["Authorization"] = f"Bearer {token}"
        except Exception as e:
            logfire.error(
                f"❌ Could not fetch identity token — Cloud Run will return 403: {e}"
            )
    return headers
