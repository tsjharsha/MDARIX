"""Flatten the application's routes, including nested included routers, for security sweeps."""

from __future__ import annotations

from fastapi.routing import APIRoute


def _prefix(included) -> str:
    context = getattr(included, "include_context", None)
    return getattr(context, "prefix", "") or ""


def api_routes(app) -> list[tuple[str, APIRoute]]:
    """Every APIRoute with its full path (prefixes of the routers it was included through applied)."""
    found: list[tuple[str, APIRoute]] = []

    def walk(routes, prefix: str) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                path = route.path if route.path.startswith(prefix) else prefix + route.path
                found.append((path, route))
            elif type(route).__name__ == "_IncludedRouter":
                walk(route.original_router.routes, prefix + _prefix(route))

    walk(app.routes, "")
    return found
