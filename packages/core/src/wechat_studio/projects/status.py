"""Article project status transitions."""

from __future__ import annotations

from wechat_studio.errors import StatusTransitionError


STATUSES = (
    "DRAFTING",
    "PLAN_CONFIRMED",
    "CONTENT_READY",
    "READY_FOR_USER_WECHAT_VALIDATION",
    "WECHAT_VALIDATED",
    "NEEDS_REVISION",
)

ALLOWED_TRANSITIONS = {
    "DRAFTING": {"PLAN_CONFIRMED", "NEEDS_REVISION"},
    "PLAN_CONFIRMED": {"CONTENT_READY", "DRAFTING", "NEEDS_REVISION"},
    "CONTENT_READY": {"READY_FOR_USER_WECHAT_VALIDATION", "PLAN_CONFIRMED", "NEEDS_REVISION"},
    "READY_FOR_USER_WECHAT_VALIDATION": {"WECHAT_VALIDATED", "NEEDS_REVISION", "CONTENT_READY"},
    "WECHAT_VALIDATED": {"NEEDS_REVISION"},
    "NEEDS_REVISION": {"DRAFTING", "PLAN_CONFIRMED", "CONTENT_READY"},
}


def transition_status(current: str, target: str, *, user_confirmed: bool = False) -> str:
    if current == target:
        return current
    if current not in ALLOWED_TRANSITIONS or target not in ALLOWED_TRANSITIONS[current]:
        raise StatusTransitionError(
            f"Cannot transition article status from {current} to {target}.",
            context={"current": current, "target": target},
        )
    if target == "WECHAT_VALIDATED" and not user_confirmed:
        raise StatusTransitionError(
            "WECHAT_VALIDATED requires explicit user confirmation.",
            context={"current": current, "target": target, "user_confirmed": False},
        )
    return target
