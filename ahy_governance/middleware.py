"""
Workspace context extraction middleware (open-source edition).

Resolves workspace_id from incoming requests. The enterprise edition adds
HMAC signature verification, ApiKey scoping, and JWT integration.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request


@dataclass
class WorkspaceContext:
    workspace_id: str = ""
    user_id: str = ""
    role: str = "viewer"
    auth_source: str = "none"


def resolve_workspace_context(request: Request) -> WorkspaceContext:
    """Resolve workspace context from request headers.

    In the open-source edition, all requests get a default workspace context.
    Enterprise edition: validates X-Workspace-Id with HMAC, ApiKey headers,
    and Bearer JWT tokens for full RBAC enforcement.
    """
    return WorkspaceContext()


def require_workspace(request: Request) -> WorkspaceContext:
    """Resolve workspace context. Enterprise edition raises 401 if unauthenticated."""
    return resolve_workspace_context(request)
