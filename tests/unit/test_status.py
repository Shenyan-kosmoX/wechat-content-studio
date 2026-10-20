from __future__ import annotations

import pytest

from wechat_studio.errors import StatusTransitionError
from wechat_studio.projects.status import transition_status


def test_happy_path_status_transitions() -> None:
    status = "DRAFTING"
    for target in (
        "PLAN_CONFIRMED",
        "CONTENT_READY",
        "READY_FOR_USER_WECHAT_VALIDATION",
    ):
        status = transition_status(status, target)
    assert status == "READY_FOR_USER_WECHAT_VALIDATION"


def test_wechat_validated_requires_user_confirmation() -> None:
    with pytest.raises(StatusTransitionError):
        transition_status("READY_FOR_USER_WECHAT_VALIDATION", "WECHAT_VALIDATED")
    assert (
        transition_status(
            "READY_FOR_USER_WECHAT_VALIDATION",
            "WECHAT_VALIDATED",
            user_confirmed=True,
        )
        == "WECHAT_VALIDATED"
    )


def test_invalid_status_jump_is_rejected() -> None:
    with pytest.raises(StatusTransitionError):
        transition_status("DRAFTING", "WECHAT_VALIDATED", user_confirmed=True)
