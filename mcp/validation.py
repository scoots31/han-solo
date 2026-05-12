"""
Write contract enforcement layer.
Claude cannot touch user management, key management, or visibility settings.
Any tool call that targets protected operations is blocked here before reaching Letta.
"""
from .config import UserIdentity, Role

# Block labels that only the owner role can write
OWNER_ONLY_BLOCKS = {
    "user_registry",
    "api_keys",
    "visibility_settings",
    "billing",
}

# Block label prefixes that are Ren's private layer — only Ren's own session writes these
REN_PRIVATE_PREFIXES = (
    "ren_self_",
)


class ValidationError(Exception):
    pass


def assert_can_write_block(label: str, user: UserIdentity) -> None:
    """Raise ValidationError if the user is not permitted to write to this block."""
    if label in OWNER_ONLY_BLOCKS and not user.is_owner():
        raise ValidationError(
            f"Block '{label}' is restricted to owner-level users. "
            f"User '{user.id}' has role '{user.role}'."
        )


def assert_can_write_signal(subject_id: str, user: UserIdentity) -> None:
    """
    Raise ValidationError if the user cannot write a signal about the given subject.
    Signals about a person can only be written by Ren (the MCP server itself acting on
    session close) or the owner. Collaborators can write signals about projects but not
    about people's portraits.
    """
    portrait_subjects = {"scott", "ted", "ren"}
    if subject_id in portrait_subjects and not user.is_owner():
        raise ValidationError(
            f"Portrait signals about '{subject_id}' can only be written by owner-level users. "
            f"User '{user.id}' has role '{user.role}'."
        )


def assert_can_read_tier(tier: str, user: UserIdentity) -> None:
    """Raise ValidationError if the user cannot read content at this visibility tier."""
    from .config import VisibilityTier
    try:
        tier_enum = VisibilityTier(tier)
    except ValueError:
        raise ValidationError(f"Unknown visibility tier: '{tier}'")

    if not user.can_read(tier_enum):
        raise ValidationError(
            f"User '{user.id}' does not have clearance for tier '{tier}'."
        )
