import os
from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    OWNER = "owner"
    COLLABORATOR = "collaborator"


class VisibilityTier(str, Enum):
    PRIVATE = "private"          # owner only
    SHARED = "shared"            # all builders
    CLIENT_JOINT = "client_joint"      # builders + designated client view
    CLIENT_EXCLUSIVE = "client_exclusive"  # owner only, other party sees name only


@dataclass
class UserIdentity:
    id: str
    name: str
    role: Role
    # which visibility tiers this user can read content from
    visibility_clearance: list[VisibilityTier] = field(default_factory=list)

    def can_read(self, tier: VisibilityTier) -> bool:
        return tier in self.visibility_clearance

    def is_owner(self) -> bool:
        return self.role == Role.OWNER


# Letta connection
LETTA_URL = os.environ["LETTA_URL"]
LETTA_API_KEY = os.environ["LETTA_API_KEY"]

# Agent name — looked up by name on startup, created if missing
REN_AGENT_NAME = os.environ.get("REN_AGENT_NAME", "ren-v2")

# Optional: hardcode agent ID to skip the lookup entirely.
# Set REN_AGENT_ID in Render env vars to pin to a specific agent.
REN_AGENT_ID = os.environ.get("REN_AGENT_ID")

# MCP server port
PORT = int(os.environ.get("PORT", "8000"))

# Token → UserIdentity registry
# Tokens are stored as env vars: USER_TOKEN_SCOTT, USER_TOKEN_TED, etc.
# Each maps to a user definition. Add new users by adding env vars + entries here.
def _build_token_registry() -> dict[str, UserIdentity]:
    users = {
        "scott": UserIdentity(
            id="scott",
            name="Scott",
            role=Role.OWNER,
            visibility_clearance=[
                VisibilityTier.PRIVATE,
                VisibilityTier.SHARED,
                VisibilityTier.CLIENT_JOINT,
                VisibilityTier.CLIENT_EXCLUSIVE,
            ],
        ),
        "ted": UserIdentity(
            id="ted",
            name="Ted",
            role=Role.COLLABORATOR,
            visibility_clearance=[
                VisibilityTier.SHARED,
                VisibilityTier.CLIENT_JOINT,
            ],
        ),
    }

    registry: dict[str, UserIdentity] = {}
    for user_id, identity in users.items():
        env_key = f"USER_TOKEN_{user_id.upper()}"
        token = os.environ.get(env_key)
        if token:
            registry[token] = identity

    return registry


TOKEN_REGISTRY: dict[str, UserIdentity] = _build_token_registry()
