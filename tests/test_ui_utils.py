"""Unit tests for ui_utils helpers (no Rich console assertions)."""

from __future__ import annotations

from pathlib import Path

from ui_utils import parse_linter_to_bug_rows, write_html_report


def test_parse_linter_ok_empty() -> None:
    assert parse_linter_to_bug_rows("LINTER: OK") == []
    assert parse_linter_to_bug_rows("LINTER: flake8 not installed, skipped.") == []


def test_parse_linter_flake8_line() -> None:
    raw = "LINTER:\nfoo.py:12:5: E501 line too long (99 > 88)\n"
    rows = parse_linter_to_bug_rows(raw)
    assert len(rows) >= 1
    err_type, line_no, severity, rec = rows[0]
    assert line_no == "12"
    assert "E501" in err_type or "E501" in rec


def test_write_html_report_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "r.html"
    task = "Task <script>"
    iterations = [
        {
            "i": 0,
            "code": "print(1)",
            "linter": "LINTER: OK",
            "runtime": "SUCCESS",
            "qa": "VERDICT: ISSUES",
            "qa_pass": False,
            "linter_ok": True,
        }
    ]
    write_html_report(str(out), task, iterations, achieved=False)
    text = out.read_text(encoding="utf-8")
    assert "Task &lt;script&gt;" in text
    assert "Iteration 0" in text
    assert "print(1)" in text
    assert "VERDICT: ISSUES" in text
