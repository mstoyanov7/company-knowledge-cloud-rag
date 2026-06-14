"""Markdown polish of generated answers: bold spans, code fences, inline code.

Covers the answer inconsistencies observed in live use: bold markers closed in
the middle of a value (half-bold "10:00"), ordinary prose wrapped in a code
box, and plain phrases wrapped in inline code.
"""

from rag_api.services.answer_service import (
    _fix_broken_bold_spans,
    _merge_adjacent_code_fences,
    _strip_prose_inline_code,
    _unwrap_prose_code_fences,
)


# --------------------------------------------------------------------------- #
# broken bold spans
# --------------------------------------------------------------------------- #
def test_bold_closed_inside_clock_time_is_extended_to_whole_value() -> None:
    fixed = _fix_broken_bold_spans("The daily standup is at **10**:00 every day.")
    assert "**10:00**" in fixed
    assert "**10**:00" not in fixed


def test_bold_closed_after_colon_inside_time() -> None:
    fixed = _fix_broken_bold_spans("**The daily standup is at 10:**00 every day.")
    assert fixed == "**The daily standup is at 10:00** every day."


def test_bold_closed_inside_percentage_and_version() -> None:
    assert "**80%**" in _fix_broken_bold_spans("coverage of **80**% on the diff")
    assert "**3.24**" in _fix_broken_bold_spans("Flutter **3**.24 is supported")


def test_unpaired_bold_marker_is_removed() -> None:
    fixed = _fix_broken_bold_spans("The **stipend is paid weekly.")
    assert "**" not in fixed
    assert "stipend is paid weekly" in fixed


def test_empty_bold_is_removed_and_valid_bold_untouched() -> None:
    assert _fix_broken_bold_spans("a ** ** b") == "a   b"
    text = "Use **bold phrases** normally and **10:00** stays intact."
    assert _fix_broken_bold_spans(text) == text


def test_bold_inside_code_fence_is_untouched() -> None:
    text = "```python\nvalue = '**10**:00'\n```"
    assert _fix_broken_bold_spans(text) == text


# --------------------------------------------------------------------------- #
# prose wrongly fenced as code
# --------------------------------------------------------------------------- #
def test_plain_sentence_in_code_fence_is_unwrapped() -> None:
    text = (
        "Here is the policy:\n\n```\nThe daily standup is held at 10:00 in the "
        "team channel and it lasts fifteen minutes.\n```"
    )
    fixed = _unwrap_prose_code_fences(text)
    assert "```" not in fixed
    assert "held at 10:00 in the team channel" in fixed


def test_real_commands_stay_fenced() -> None:
    text = "```bash\ngit clone repo\npip install -e .\n```"
    assert _unwrap_prose_code_fences(text) == text


def test_config_and_env_lines_stay_fenced() -> None:
    text = "```\nGRAPH_ONENOTE_CLIENT_ID=abc123\n```"
    assert _unwrap_prose_code_fences(text) == text


def test_short_or_ambiguous_fences_are_left_alone() -> None:
    text = "```\nnw doctor\n```"
    assert _unwrap_prose_code_fences(text) == text


# --------------------------------------------------------------------------- #
# plain phrases wrongly wrapped in inline code
# --------------------------------------------------------------------------- #
def test_plain_phrase_inline_code_is_unwrapped() -> None:
    fixed = _strip_prose_inline_code("Submit the request in `the portal for all new employees` today.")
    assert "`" not in fixed
    assert "the portal for all new employees" in fixed


def test_identifiers_paths_and_commands_keep_backticks() -> None:
    for text in (
        "Set `default_model_name` in the settings.",
        "Read `secret/billing/stripe-test` from the vault.",
        "Run `docker compose up -d` first.",
        "The `nw doctor` check must be green.",
    ):
        assert _strip_prose_inline_code(text) == text


# --------------------------------------------------------------------------- #
# adjacent code fences of the same language merge into one block
# --------------------------------------------------------------------------- #
def test_adjacent_same_language_fences_merge() -> None:
    text = "```bash\ngit clone repo\n```\n\n```bash\npip install -e .\n```"
    merged = _merge_adjacent_code_fences(text)
    assert merged.count("```") == 2
    assert "git clone repo" in merged and "pip install -e ." in merged
