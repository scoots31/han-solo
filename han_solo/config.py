import os
from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    OWNER = "owner"
    COLLABORATOR = "collaborator"
    AGENT = "agent"  # Ren and future AI agents — full read clearance, no human role


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

# Anthropic API — used for inline synthesis at rollover and by the cron script
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ElevenLabs TTS — voice output for Ren
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")

# MCP server port
PORT = int(os.environ.get("PORT", "8000"))

# Bearer token Letta uses to authenticate when calling this MCP server's tools/list.
# Required for /api/admin/sync-mcp-tools to re-register the server with Letta.
# Set to the same value as USER_TOKEN_SCOTT in Render env vars.
MCP_SERVER_TOKEN = os.environ.get("MCP_SERVER_TOKEN", "")

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
        "ren": UserIdentity(
            id="ren",
            name="Ren",
            role=Role.AGENT,
            visibility_clearance=[
                VisibilityTier.PRIVATE,
                VisibilityTier.SHARED,
                VisibilityTier.CLIENT_JOINT,
                VisibilityTier.CLIENT_EXCLUSIVE,
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
