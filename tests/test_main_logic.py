"""Unit tests for main.py helpers and BugHunter logic that does not call LLMs or Docker."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

import main


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("VERDICT: PASS", True),
        ("verdict: pass\nmore", True),
        ("Some text\nVERDICT:  PASS  \n", True),
        ("VERDICT: ISSUES", False),
        ("verdict: issues", False),
        ("No structured verdict but PASS in legacy", True),
        ("PASS without verdict line", True),
        ("only issues mentioned, no verdict word", False),
    ],
)
def test_qa_verdict_passes(text: str, expected: bool) -> None:
    assert main.qa_verdict_passes(text) is expected


def test_qa_verdict_pass_issues_wins_over_legacy_pass() -> None:
    """Explicit ISSUES line must not be treated as pass via substring."""
    text = "Looks good overall PASS but VERDICT: ISSUES\nfix x"
    assert main.qa_verdict_passes(text) is False


def _minimal_config() -> dict:
    return {"models": {}, "settings": {}, "prompts": {}}


@pytest.mark.parametrize(
    ("raw", "expected_substr"),
    [
        ("```python\nx = 1\n```", "x = 1"),
        ("```Python\ny = 2\n```", "y = 2"),
        ("Intro\n```\nz = 3\n```", "z = 3"),
        ("no fences", "no fences"),
    ],
)
def test_strip_markdown(raw: str, expected_substr: str) -> None:
    h = main.BugHunter(_minimal_config())
    out = h._strip_markdown(raw)
    assert expected_substr in out
    assert out.strip() == out or "\n" in raw


def test_load_config_ok(tmp_path: Path) -> None:
    p = tmp_path / "cfg.yml"
    data = {"models": {"dev": "m"}, "settings": {"max_iterations": 2}}
    p.write_text(yaml.dump(data), encoding="utf-8")
    loaded = main.load_config(str(p))
    assert loaded["models"]["dev"] == "m"
    assert loaded["settings"]["max_iterations"] == 2


def test_load_config_empty_exits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    p = tmp_path / "empty.yml"
    p.write_text("", encoding="utf-8")

    def boom(code: int) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", boom)
    with pytest.raises(SystemExit):
        main.load_config(str(p))


def test_load_config_missing_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(code: int) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", boom)
    with pytest.raises(SystemExit):
        main.load_config(str(Path("/nonexistent/bughunter_config_xyz.yml")))


def test_parser_preset_choices() -> None:
    parser = main._build_parser()
    preset = next(a for a in parser._actions if a.dest == "preset")
    assert preset.choices is not None
    assert set(preset.choices) == set(main.PRESET_TASKS.keys())


def test_bug_hunter_model_overrides() -> None:
    cfg = {
        "models": {"dev": "dev-from-yaml", "qa": "qa-from-yaml"},
        "settings": {},
        "prompts": {},
    }
    h = main.BugHunter(cfg, dev_model_override="d-override", qa_model_override="q-override")
    assert h.dev_model == "d-override"
    assert h.qa_model == "q-override"
