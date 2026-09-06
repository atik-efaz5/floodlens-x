"""DEMO identity provider and RBAC.

Not a production IdP. Tokens are `demo.<role>` bearer strings so the UI can
switch roles without a hidden backdoor. Real JWT/OIDC can replace encode/decode.
"""

from __future__ import annotations

from typing import FrozenSet, Optional

ROLES = ("general", "emergency", "researcher", "admin")

ROLE_PERMISSIONS = {
    "general": frozenset(
        {
            "map.read",
            "forecast.read",
            "risk.read",
            "alerts.read",
            "alerts.write",
            "places.write",
            "places.read",
            "explain.read",
            "assistant.chat",
            "reports.write",
            "reports.read",
            "shares.read",
            "shares.write",
            "impact.read",
        }
    ),
    "emergency": frozenset(
        {
            "map.read",
            "forecast.read",
            "risk.read",
            "alerts.read",
            "alerts.write",
            "places.write",
            "places.read",
            "explain.read",
            "assistant.chat",
            "reports.write",
            "reports.read",
            "shares.read",
            "shares.write",
            "impact.read",
            "resources.read",
            "command.read",
            "jobs.write",
            "jobs.read",
            "scenarios.write",
        }
    ),
    "researcher": frozenset(
        {
            "map.read",
            "forecast.read",
            "risk.read",
            "alerts.read",
            "alerts.write",
            "places.write",
            "places.read",
            "explain.read",
            "assistant.chat",
            "reports.write",
            "reports.read",
            "shares.read",
            "shares.write",
            "jobs.write",
            "scenarios.write",
            "research.read",
            "jobs.read",
            "impact.read",
        }
    ),
    "admin": frozenset({"*"}),
}


def encode_demo_token(role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role}")
    return f"demo.{role}"


ANONYMOUS_PERMISSIONS = frozenset(
    {
        "map.read",
        "forecast.read",
        "risk.read",
        "explain.read",
        "impact.read",
        "reports.read",
        "shares.read",
        "alerts.read",
        "places.read",
        "assistant.chat",
    }
)


def parse_bearer(authorization: Optional[str]) -> tuple[Optional[str], str]:
    """Return (role, status) where status is ok | missing | invalid."""
    if not authorization:
        return None, "missing"
    value = authorization.removeprefix("Bearer ").strip()
    if value.startswith("demo."):
        role = value.split(".", 1)[1]
        if role in ROLES:
            return role, "ok"
    return None, "invalid"


def decode_demo_token(token: Optional[str]) -> str:
    role, status = parse_bearer(token)
    if status == "ok" and role:
        return role
    return "general"


def has_permission(role: str, permission: str) -> bool:
    grants: FrozenSet[str] = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["general"])
    return "*" in grants or permission in grants


def identity_from_authorization(authorization: Optional[str]) -> str:
    """Server-side owner identity. Do not trust client-supplied user_id."""
    return f"demo.{decode_demo_token(authorization)}"
