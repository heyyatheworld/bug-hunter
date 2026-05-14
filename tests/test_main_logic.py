"""Unit tests for main.py helpers and BugHunter logic that does not call LLMs or Docker."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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


def test_model_available_on_host() -> None:
    installed = {"qwen2.5-coder:7b", "llama3:latest", "mistral"}
    assert main.model_available_on_host("qwen2.5-coder:7b", installed) is True
    assert main.model_available_on_host("llama3", installed) is True
    assert main.model_available_on_host("mistral", installed) is True
    assert main.model_available_on_host("missing:tag", installed) is False
    assert main.model_available_on_host("llama3:8b", installed) is False


def test_check_ollama_and_models_skip_skips_list(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise AssertionError("ollama.list should not be called when skip=True")

    monkeypatch.setattr(main.ollama, "list", boom)
    main.check_ollama_and_models("any", "any", skip=True)


def test_check_ollama_exits_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> None:
        raise ConnectionError("refused")

    monkeypatch.setattr(main.ollama, "list", fail)
    monkeypatch.setattr(sys, "exit", lambda c: (_ for _ in ()).throw(SystemExit(c)))
    with pytest.raises(SystemExit):
        main.check_ollama_and_models("a", "b", skip=False)


def test_check_ollama_exits_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_resp = SimpleNamespace(models=[SimpleNamespace(model="foo:bar")])
    monkeypatch.setattr(main.ollama, "list", lambda: fake_resp)
    monkeypatch.setattr(sys, "exit", lambda c: (_ for _ in ()).throw(SystemExit(c)))
    with pytest.raises(SystemExit):
        main.check_ollama_and_models("not-there", "not-there", skip=False)


def test_ollama_chat_or_exit_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_chat(**kwargs: object) -> dict:
        assert kwargs.get("model") == "m1"
        return {"message": {"content": "ok"}}

    monkeypatch.setattr(main.ollama, "chat", fake_chat)
    out = main.ollama_chat_or_exit(
        model="m1",
        messages=[{"role": "user", "content": "hi"}],
        phase="DEV",
        iteration=0,
    )
    assert out["message"]["content"] == "ok"


def test_ollama_chat_or_exit_failure_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kwargs: object) -> None:
        raise ConnectionError("refused")

    monkeypatch.setattr(main.ollama, "chat", boom)
    monkeypatch.setattr(sys, "exit", lambda c: (_ for _ in ()).throw(SystemExit(c)))
    with pytest.raises(SystemExit) as ei:
        main.ollama_chat_or_exit(
            model="m1",
            messages=[{"role": "user", "content": "x"}],
            phase="QA",
            iteration=1,
        )
    assert ei.value.args[0] == 2


def test_parser_version_prints_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    parser = main._build_parser()
    with pytest.raises(SystemExit) as ei:
        parser.parse_args(["--version"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert main.__version__ in out
    assert "BugHunter" in out


def test_parser_skip_model_check_flag() -> None:
    parser = main._build_parser()
    args = parser.parse_args(["--skip-model-check"])
    assert args.skip_model_check is True
