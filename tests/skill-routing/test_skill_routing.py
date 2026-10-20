from __future__ import annotations

from pathlib import Path

import yaml


ROUTING_ROOT = Path(__file__).parent
SKILLS = {
    "wechat-compose-article",
    "wechat-distill-style",
    "wechat-manage-style-library",
}


def load_cases(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def test_routing_fixtures_have_required_coverage_and_unique_ids() -> None:
    all_ids: set[str] = set()
    positive_prompts: dict[str, str] = {}
    fixture_paths = sorted(ROUTING_ROOT.glob("wechat-*.yaml"))

    assert {path.stem for path in fixture_paths} == SKILLS
    for path in fixture_paths:
        document = load_cases(path)
        assert document["skill"] == path.stem
        assert len(document["should_trigger"]) >= 10
        assert len(document["should_not_trigger"]) >= 10
        assert len(document["cross_skill_confusions"]) >= 3

        for section in ("should_trigger", "should_not_trigger"):
            for case in document[section]:
                assert set(case) >= {"id", "prompt", "reason"}
                assert case["id"] not in all_ids
                all_ids.add(case["id"])
                assert str(case["prompt"]).strip()
                assert str(case["reason"]).strip()

        for case in document["should_trigger"]:
            prompt = case["prompt"].strip()
            assert prompt not in positive_prompts
            positive_prompts[prompt] = document["skill"]


def test_negative_and_confusion_targets_are_explicit_and_valid() -> None:
    for path in sorted(ROUTING_ROOT.glob("wechat-*.yaml")):
        document = load_cases(path)
        current = document["skill"]
        for case in document["should_not_trigger"]:
            target = case.get("expected_skill")
            assert target == "none" or target in SKILLS - {current}

        for case in document["cross_skill_confusions"]:
            assert str(case["prompt"]).strip()
            assert str(case["reason"]).strip()
            if "expected_skill" in case:
                assert case["expected_skill"] in SKILLS
            else:
                sequence = case.get("expected_sequence")
                assert isinstance(sequence, list) and len(sequence) >= 2
                assert all(skill in SKILLS for skill in sequence)


def test_skill_descriptions_name_their_exclusions() -> None:
    plugin_skills = (
        Path(__file__).parents[2]
        / "plugins"
        / "wechat-content-studio"
        / "skills"
    )
    for skill in SKILLS:
        text = (plugin_skills / skill / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = yaml.safe_load(text.split("---", 2)[1])
        description = frontmatter["description"]
        assert "Use when" in description
        assert "Do not use" in description
