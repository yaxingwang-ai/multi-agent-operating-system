"""Data contracts between MAOS workflow stages (V1.2).

Agents return Markdown. Before one stage's output is passed to the next, it
is parsed into its required level-2 sections, and rejected if any is
missing, duplicated, out of order, unexpected, or empty, or if a fenced code
block is left unclosed.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

# Longest heading text quoted back in a validation problem.
_MAX_QUOTED_HEADING = 60

# Most problems included in an OutputValidationError message.
MAX_REPORTED_PROBLEMS = 5

# A level-2 ATX heading: up to three spaces, then "##", with optional closing
# hashes ("## Name ##").
_HEADING_RE = re.compile(r"^ {0,3}##[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
# A fence line: up to three spaces, then ``` or ~~~ (or longer), then the rest.
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


class OutputValidationError(Exception):
    """Raised when agent output does not match its required sections.

    ``problems`` holds every problem; the message lists at most
    MAX_REPORTED_PROBLEMS of them, so it stays short.
    """

    def __init__(self, problems: Sequence[str]):
        self.problems = tuple(problems)
        super().__init__(self.summary())

    def summary(self) -> str:
        shown = "; ".join(self.problems[:MAX_REPORTED_PROBLEMS])
        hidden = len(self.problems) - MAX_REPORTED_PROBLEMS
        if hidden > 0:
            shown += f"; and {hidden} more problem{'s' if hidden > 1 else ''}"
        return shown


class EmptyAnalysisOutputError(Exception):
    """Raised when the Investment Analyst run finishes without any output."""


def _freeze_sections(stage_output) -> None:
    """Store a read-only copy of ``sections``, so neither the object nor the
    caller's original mapping can change it later."""
    sections = MappingProxyType(dict(stage_output.sections))
    object.__setattr__(stage_output, "sections", sections)


@dataclass(frozen=True)
class WorkflowRequest:
    """The user's request: the input to the whole workflow.

    Validated on creation, so every interface (CLI now, API later) gets the
    same rules. Values are stripped; blank optional fields become None.
    """

    request: str
    subject: str | None = None
    topic: str | None = None
    period: str | None = None

    def __post_init__(self):
        if not isinstance(self.request, str):
            raise ValueError("request must be a string")
        if not self.request.strip():
            raise ValueError("request must not be empty")
        object.__setattr__(self, "request", self.request.strip())

        for name in ("subject", "topic", "period"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be a string or None")
            object.__setattr__(self, name, (value or "").strip() or None)


@dataclass(frozen=True)
class ResearchReport:
    """Validated Research Agent output, passed to the Investment Analyst."""

    sections: Mapping[str, str]
    markdown: str

    def __post_init__(self):
        _freeze_sections(self)


@dataclass(frozen=True)
class InvestmentAnalysis:
    """Validated Investment Analyst output, passed to the final report."""

    sections: Mapping[str, str]
    markdown: str

    def __post_init__(self):
        _freeze_sections(self)


@dataclass(frozen=True)
class WorkflowResult:
    """Everything one successful workflow run produced."""

    request: WorkflowRequest
    research: ResearchReport
    analysis: InvestmentAnalysis
    report_markdown: str


def _quote(heading: str) -> str:
    if len(heading) > _MAX_QUOTED_HEADING:
        heading = heading[:_MAX_QUOTED_HEADING] + "..."
    return repr(heading)


def _fence_blocks(lines: Sequence[str]) -> list[tuple[int, int | None]]:
    """Return (opening, closing) line indexes of each fenced code block.

    A block closes on a fence of the same character, at least as long, with
    nothing after it. The closing index is None if the block never closes.
    """
    blocks = []
    opener = start = None
    for i, line in enumerate(lines):
        match = _FENCE_RE.match(line)
        if not match:
            continue
        fence, rest = match.groups()
        if opener is None:
            # A backtick fence's info string cannot contain backticks.
            if not (fence[0] == "`" and "`" in rest):
                opener, start = fence, i
        elif fence[0] == opener[0] and len(fence) >= len(opener) and not rest.strip():
            blocks.append((start, i))
            opener = None
    if opener is not None:
        blocks.append((start, None))
    return blocks


def parse_sections(markdown: str, expected: Sequence[str]) -> Mapping[str, str]:
    """Split Markdown into its required level-2 sections.

    Line endings are normalized, text before the first level-2 heading is
    ignored, a code fence wrapping the whole output is removed, and headings
    inside fenced code blocks are treated as body text. Every other deviation
    from ``expected`` is reported, including an unclosed code fence, which
    would otherwise break the final report.

    Returns:
        Read-only section bodies keyed by heading, in ``expected`` order.

    Raises:
        OutputValidationError: lists every problem found.
    """
    text = (markdown or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise OutputValidationError(["output is empty"])

    lines = text.split("\n")
    blocks = _fence_blocks(lines)
    if blocks and blocks[0] == (0, len(lines) - 1):
        lines = lines[1:-1]
        blocks = _fence_blocks(lines)
    in_code = set()
    for start, end in blocks:
        in_code.update(range(start, len(lines) if end is None else end + 1))

    found = []
    bodies = {}
    problems = []
    current = None
    location = "before the first section"

    for i, line in enumerate(lines):
        match = None if i in in_code else _HEADING_RE.match(line)
        if match is None:
            if current is not None:
                current.append(line)
            if blocks and blocks[-1] == (i, None):
                # It hides every heading after it, so report it first.
                problems.insert(0, f"unclosed code fence {location}")
            continue
        heading = match.group(1)
        found.append(heading)
        current = None
        label = heading if heading in expected else _quote(heading)
        location = f"in section: {label}"
        if heading not in expected:
            problems.append(f"unexpected section: {label}")
        elif heading in bodies:
            problems.append(f"duplicate section: {heading}")
        else:
            bodies[heading] = current = []

    bodies = {name: "\n".join(body).strip() for name, body in bodies.items()}
    problems += [f"missing section: {name}" for name in expected if name not in bodies]
    problems += [f"empty section: {name}" for name, body in bodies.items() if not body]

    if not problems and [h for h in found if h in expected] != list(expected):
        problems.append("sections are out of order")
    if problems:
        raise OutputValidationError(problems)

    return MappingProxyType({name: bodies[name] for name in expected})
