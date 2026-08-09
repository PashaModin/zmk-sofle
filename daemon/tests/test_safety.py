"""The allowlist is the only thing standing between a button and a shell."""

from __future__ import annotations

import pytest

from soflectl.config import Config
from soflectl.safety import (
    bash_command_allowed,
    eligible_for_hardware_approval,
    strip_env_assignments,
    summarize,
)


@pytest.fixture
def cfg():
    return Config()


# -- tool allowlist ---------------------------------------------------------


def test_read_is_approvable(cfg):
    assert eligible_for_hardware_approval(cfg, "Read", {"file_path": "/tmp/x"})


def test_unknown_tool_is_not_approvable(cfg):
    assert not eligible_for_hardware_approval(cfg, "SomeNewTool", {})


def test_empty_tool_name_is_not_approvable(cfg):
    assert not eligible_for_hardware_approval(cfg, "", {})


def test_bash_is_not_on_the_tool_allowlist(cfg):
    assert "Bash" not in cfg.hardware_approvable


# -- bash prefixes ----------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    ["git status", "git diff", "git diff --staged", "npm test", "pytest", "pytest -k foo"],
)
def test_allowed_bash_prefixes(cfg, command):
    assert bash_command_allowed(cfg, command)


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "git pushed",                 # prefix of a word, not a word boundary
        "git statusfoo",
        "gitstatus",
        "sudo git status",
        "",
        "   ",
    ],
)
def test_rejected_bash_commands(cfg, command):
    assert not bash_command_allowed(cfg, command)


@pytest.mark.parametrize(
    "command",
    [
        "git diff && rm -rf /",
        "git status; rm -rf /",
        "git status | sh",
        "git status $(rm -rf /)",
        "git status `rm -rf /`",
        "git status > /etc/passwd",
        "git status\nrm -rf /",
    ],
)
def test_chained_commands_are_rejected_despite_allowed_prefix(cfg, command):
    # The prefix only means something if it describes the whole command.
    assert not bash_command_allowed(cfg, command)


def test_env_assignments_are_stripped_before_matching(cfg):
    assert bash_command_allowed(cfg, "FOO=bar git status")
    assert bash_command_allowed(cfg, "FOO=bar BAZ=qux git status")
    assert bash_command_allowed(cfg, 'FOO="a b" git status')


def test_env_assignments_cannot_smuggle_a_command(cfg):
    assert not bash_command_allowed(cfg, "FOO=bar rm -rf /")


def test_strip_env_assignments():
    assert strip_env_assignments("A=1 B=2 git log") == "git log"
    assert strip_env_assignments("git log") == "git log"
    assert strip_env_assignments("A=1") == ""


def test_whitespace_is_collapsed_before_matching(cfg):
    assert bash_command_allowed(cfg, "git    status")


def test_very_long_command_is_rejected_not_crashing(cfg):
    assert not bash_command_allowed(cfg, "x" * 4096)


def test_bash_via_eligibility_helper(cfg):
    assert eligible_for_hardware_approval(cfg, "Bash", {"command": "git status"})
    assert not eligible_for_hardware_approval(cfg, "Bash", {"command": "rm -rf /"})
    assert not eligible_for_hardware_approval(cfg, "Bash", {})


# -- summaries --------------------------------------------------------------


def test_bash_summary_keeps_the_head_of_the_command():
    # Truncating from the right leaves the dangerous part visible.
    assert summarize("Bash", {"command": "rm -rf /very/long/path"}, width=16) == "rm -rf /very/lon"


def test_file_summary_keeps_the_basename():
    assert summarize("Read", {"file_path": "/a/very/long/path/notes.md"}) == "notes.md"


def test_grep_summary_uses_the_pattern():
    assert summarize("Grep", {"pattern": "TODO"}) == "TODO"


def test_summary_collapses_whitespace():
    assert summarize("Bash", {"command": "git   \n  status"}) == "git status"


def test_summary_of_unknown_tool_is_empty():
    assert summarize("Whatever", {"x": 1}) == ""


def test_summary_handles_missing_input():
    assert summarize("Read", {}) == ""
    assert summarize("Bash", {}) == ""
