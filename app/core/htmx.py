from flask import redirect, request


def go(url):
    """Redirige también las peticiones HTMX (que no siguen un 302 como navegación)."""
    if request.headers.get("HX-Request"):
        return "", 200, {"HX-Redirect": url}
    return redirect(url)
