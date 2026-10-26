import dataclasses

import pytest

from maos.contracts import (
    InvestmentAnalysis,
    OutputValidationError,
    ResearchReport,
    WorkflowRequest,
    parse_sections,
)

EXPECTED = ("Alpha", "Beta", "Gamma")
VALID = "## Alpha\nA body.\n\n## Beta\nB body.\n\n## Gamma\nC body."


def _problems(markdown):
    with pytest.raises(OutputValidationError) as exc:
        parse_sections(markdown, EXPECTED)
    return exc.value.problems


def test_valid_output_is_parsed_in_order():
    sections = parse_sections(VALID, EXPECTED)
    assert tuple(sections) == EXPECTED
    assert sections["Beta"] == "B body."


def test_parsed_sections_are_read_only():
    sections = parse_sections(VALID, EXPECTED)
    with pytest.raises(TypeError):
        sections["Alpha"] = "changed"


@pytest.mark.parametrize("contract", [ResearchReport, InvestmentAnalysis])
def test_stage_output_sections_cannot_be_modified(contract):
    original = {"Alpha": "A body."}
    output = contract(sections=original, markdown="## Alpha\nA body.")
    with pytest.raises(TypeError):
        output.sections["Alpha"] = "changed"
    original["Alpha"] = "changed"
    original["Beta"] = "added"
    assert dict(output.sections) == {"Alpha": "A body."}


def test_multiline_bodies_and_subheadings_are_kept():
    markdown = VALID.replace("B body.", "First line.\n\n### Detail\n- point")
    assert parse_sections(markdown, EXPECTED)["Beta"] == "First line.\n\n### Detail\n- point"


def test_preamble_before_first_heading_is_ignored():
    sections = parse_sections("# Research Report\n\nIntro text.\n\n" + VALID, EXPECTED)
    assert sections["Alpha"] == "A body."


@pytest.mark.parametrize("fence", ["```", "```markdown", "```md"])
def test_single_wrapping_code_fence_is_removed(fence):
    sections = parse_sections(f"{fence}\n{VALID}\n```", EXPECTED)
    assert sections["Gamma"] == "C body."


def test_trailing_whitespace_on_headings_is_ignored():
    assert parse_sections(VALID.replace("## Beta", "##  Beta  "), EXPECTED)["Beta"] == "B body."


@pytest.mark.parametrize("markdown", [None, "", "   \n\t "], ids=["none", "empty", "blank"])
def test_empty_output_is_rejected(markdown):
    assert _problems(markdown) == ("output is empty",)


def test_output_without_headings_reports_every_section_missing():
    assert _problems("Just some prose.") == tuple(
        f"missing section: {name}" for name in EXPECTED
    )


def test_missing_section_is_reported():
    markdown = "## Alpha\nA body.\n\n## Gamma\nC body."
    assert _problems(markdown) == ("missing section: Beta",)


def test_empty_section_is_reported():
    markdown = VALID.replace("B body.", "  \n")
    assert _problems(markdown) == ("empty section: Beta",)


def test_duplicate_section_is_reported():
    assert _problems(VALID + "\n\n## Beta\nAgain.") == ("duplicate section: Beta",)


def test_unexpected_section_is_reported():
    assert _problems(VALID + "\n\n## Recommendation\nBuy.") == (
        "unexpected section: 'Recommendation'",
    )


def test_long_unexpected_heading_is_truncated():
    (problem,) = _problems(VALID + "\n\n## " + "x" * 200 + "\nbody")
    assert problem == f"unexpected section: '{'x' * 60}...'"


def test_out_of_order_sections_are_reported():
    markdown = "## Beta\nB body.\n\n## Alpha\nA body.\n\n## Gamma\nC body."
    assert _problems(markdown) == ("sections are out of order",)


def test_level_three_headings_do_not_count_as_sections():
    assert _problems("### Alpha\nA\n\n### Beta\nB\n\n### Gamma\nC") == tuple(
        f"missing section: {name}" for name in EXPECTED
    )


def test_heading_names_must_match_exactly():
    assert _problems(VALID.replace("## Beta", "## beta")) == (
        "unexpected section: 'beta'",
        "missing section: Beta",
    )


def test_every_problem_is_reported_together():
    markdown = "## Alpha\n\n## Alpha\nagain\n\n## Extra\nx"
    assert set(_problems(markdown)) == {
        "duplicate section: Alpha",
        "unexpected section: 'Extra'",
        "missing section: Beta",
        "missing section: Gamma",
        "empty section: Alpha",
    }


def test_error_message_joins_problems():
    with pytest.raises(OutputValidationError, match="missing section: Beta; missing section: Gamma"):
        parse_sections("## Alpha\nA", EXPECTED)


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "space"])
def test_workflow_request_rejects_blank_request(blank):
    with pytest.raises(ValueError):
        WorkflowRequest(blank)


def test_workflow_request_strips_values_and_drops_blank_optionals():
    request = WorkflowRequest("  Outlook ", subject=" ACME ", topic="   ", period="")
    assert request == WorkflowRequest("Outlook", subject="ACME")
    assert request.topic is None and request.period is None


@pytest.mark.parametrize("value", [None, 123, ["Outlook"]], ids=["none", "int", "list"])
def test_workflow_request_rejects_non_string_request(value):
    with pytest.raises(ValueError, match="request must be a string"):
        WorkflowRequest(value)


@pytest.mark.parametrize("field", ["subject", "topic", "period"])
def test_workflow_request_rejects_non_string_optional_fields(field):
    with pytest.raises(ValueError, match=f"{field} must be a string or None"):
        WorkflowRequest("Outlook", **{field: 2025})


def test_workflow_request_is_immutable():
    request = WorkflowRequest("Outlook", subject="ACME")
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.request = "changed"


# M1: fenced code blocks


def test_fenced_code_block_inside_a_section_is_kept():
    body = "Intro.\n\n```python\nx = 1\n```\n\nAfter."
    assert parse_sections(VALID.replace("B body.", body), EXPECTED)["Beta"] == body


@pytest.mark.parametrize("heading", ["## Example", "## Alpha", "## Gamma"])
def test_heading_inside_fenced_block_is_body_text(heading):
    body = f"See:\n```markdown\n{heading}\n```"
    assert parse_sections(VALID.replace("B body.", body), EXPECTED)["Beta"] == body


def test_tilde_fenced_block_hides_headings():
    body = "~~~\n## Example\n~~~"
    assert parse_sections(VALID.replace("B body.", body), EXPECTED)["Beta"] == body


def test_shorter_fence_does_not_close_longer_fence():
    body = "````\n```\n## Example\n```\n````"
    assert parse_sections(VALID.replace("B body.", body), EXPECTED)["Beta"] == body


def test_wrapped_output_with_inner_fenced_block_is_accepted():
    inner = VALID.replace("B body.", "~~~\ncode\n~~~")
    sections = parse_sections(f"```markdown\n{inner}\n```", EXPECTED)
    assert sections["Beta"] == "~~~\ncode\n~~~"
    assert sections["Gamma"] == "C body."


def test_inline_triple_backticks_are_not_a_fence():
    body = "Use ```inline``` code."
    assert parse_sections(VALID.replace("B body.", body), EXPECTED)["Beta"] == body


def test_unclosed_fence_wrapping_the_whole_output_is_rejected():
    problems = _problems("```markdown\n" + VALID)
    assert problems[0] == "unclosed code fence before the first section"
    assert "missing section: Alpha" in problems


def test_wrapping_fence_closed_before_trailing_text_is_rejected():
    """Was silently accepted, leaving a stray fence in the last section."""
    problems = _problems("```\n" + VALID + "\n```\nThanks")
    assert problems == tuple(f"missing section: {name}" for name in EXPECTED)


@pytest.mark.parametrize("fence", ["```", "```python", "~~~", "````"])
def test_unclosed_fence_inside_a_section_is_rejected(fence):
    problems = _problems(VALID.replace("B body.", f"Code:\n{fence}\nx = 1"))
    assert problems == ("unclosed code fence in section: Beta", "missing section: Gamma")


def test_unclosed_fence_in_last_section_is_rejected():
    assert _problems(VALID + "\n```") == ("unclosed code fence in section: Gamma",)


@pytest.mark.parametrize(
    "closer", ["~~~", "``", "``` text"], ids=["other-char", "too-short", "info-string"]
)
def test_fence_only_closes_on_a_matching_fence(closer):
    problems = _problems(VALID + f"\n```\ncode\n{closer}")
    assert problems == ("unclosed code fence in section: Gamma",)


def test_unclosed_fence_in_unexpected_section_names_it():
    problems = _problems(VALID + "\n\n## Extra\n```")
    assert problems[0] == "unclosed code fence in section: 'Extra'"


# M2: headings


def test_crlf_line_endings_are_normalized():
    sections = parse_sections(VALID.replace("\n", "\r\n"), EXPECTED)
    assert dict(sections) == dict(parse_sections(VALID, EXPECTED))


def test_bare_cr_line_endings_are_normalized():
    assert parse_sections(VALID.replace("\n", "\r"), EXPECTED)["Gamma"] == "C body."


@pytest.mark.parametrize("closing", [" #", " ##", " ###", "\t##", " ## "])
def test_closing_hashes_are_ignored(closing):
    sections = parse_sections(VALID.replace("## Beta", f"## Beta{closing}"), EXPECTED)
    assert sections["Beta"] == "B body."


def test_closing_hashes_need_a_preceding_space():
    assert _problems(VALID.replace("## Beta", "## Beta##")) == (
        "unexpected section: 'Beta##'",
        "missing section: Beta",
    )


@pytest.mark.parametrize("indent", [" ", "  ", "   "])
def test_headings_indented_up_to_three_spaces_are_recognised(indent):
    sections = parse_sections(VALID.replace("## Gamma", f"{indent}## Gamma"), EXPECTED)
    assert sections["Gamma"] == "C body."


@pytest.mark.parametrize("indent", [" ", "  ", "   "])
def test_indented_unexpected_heading_is_rejected(indent):
    """Renders as a level-2 heading, so it must not slip into a section body."""
    assert _problems(VALID.replace("B body.", f"B body.\n{indent}## Extra\nmore")) == (
        "unexpected section: 'Extra'",
    )


def test_heading_indented_four_spaces_is_body_text():
    body = "B body.\n    ## Extra"
    assert parse_sections(VALID.replace("B body.", body), EXPECTED)["Beta"] == body


@pytest.mark.parametrize("variant", ["**Beta**", "1. Beta", "Beta:"])
def test_bold_numbered_and_punctuated_headings_are_still_rejected(variant):
    assert _problems(VALID.replace("## Beta", f"## {variant}")) == (
        f"unexpected section: {variant!r}",
        "missing section: Beta",
    )


# L1: bounded messages


def test_message_lists_at_most_five_problems_plus_a_count():
    problems = [f"missing section: S{i}" for i in range(8)]
    exc = OutputValidationError(problems)
    assert exc.problems == tuple(problems)
    assert str(exc) == "; ".join(problems[:5]) + "; and 3 more problems"
    assert exc.summary() == str(exc)


def test_message_with_one_extra_problem_is_singular():
    exc = OutputValidationError([f"p{i}" for i in range(6)])
    assert str(exc) == "p0; p1; p2; p3; p4; and 1 more problem"


def test_message_with_exactly_five_problems_has_no_count():
    assert str(OutputValidationError([f"p{i}" for i in range(5)])) == "p0; p1; p2; p3; p4"


def test_many_unexpected_headings_give_a_bounded_message():
    markdown = "\n".join(f"## {'X' * 200}{i}\nz" for i in range(100)) + "\n" + VALID
    with pytest.raises(OutputValidationError) as exc:
        parse_sections(markdown, EXPECTED)
    assert len(exc.value.problems) == 100
    assert str(exc.value).endswith("; and 95 more problems")
    assert len(str(exc.value)) < 500
