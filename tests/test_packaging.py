"""Command registration in pyproject.toml, checked without installing."""

from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

import maos
from maos import cli, workflow_cli

tomllib = pytest.importorskip("tomllib")  # Python 3.11+

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


@pytest.fixture(scope="module")
def project():
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]


def test_console_scripts_are_registered(project):
    assert project["scripts"] == {
        "maos-research": "maos.cli:main",
        "maos-workflow": "maos.workflow_cli:main",
    }


@pytest.mark.parametrize(
    ("name", "expected"),
    [("maos-research", cli.main), ("maos-workflow", workflow_cli.main)],
)
def test_console_scripts_resolve_to_cli_main(project, name, expected):
    """Load each entry point the same way an installed launcher would."""
    entry_point = EntryPoint(name, project["scripts"][name], "console_scripts")
    assert entry_point.load() is expected


def test_version_is_read_from_the_package(project):
    assert "version" in project["dynamic"]
    assert maos.__version__ == "1.2.0"


def test_no_new_runtime_dependencies(project):
    assert project["dependencies"] == [
        "openai==3.33.0",
        "openai-agents==0.23.1",
        "python-dotenv==1.2.4",
    ]
