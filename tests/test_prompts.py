"""Guardrail: every prompt template must be a valid string.Template.

load_prompt() renders templates with Template.substitute(), which raises
ValueError("Invalid placeholder") on a bare `$` (e.g. a literal "$34.80T" money
example). That blew up the executor and summarizer prompts silently — every
interpretation failed into a raw-data dump and the summarizer fell back on every
run. Literal dollar signs must be escaped as `$$`. This test catches the whole
class of regressions across all prompts without needing each template's kwargs.
"""
import os
from string import Template

import pytest

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "prompts")

_md_files = [
    os.path.join(root, f)
    for root, _, files in os.walk(PROMPTS_DIR)
    for f in files
    if f.endswith(".md")
]


@pytest.mark.parametrize("path", _md_files, ids=lambda p: os.path.relpath(p, PROMPTS_DIR))
def test_prompt_has_no_invalid_placeholder(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    # is_valid() is False when a bare/invalid `$` placeholder is present.
    assert Template(text).is_valid(), (
        f"{os.path.relpath(path, PROMPTS_DIR)} has an invalid $ placeholder "
        f"(escape literal dollar signs as $$)"
    )


def test_found_prompt_files():
    assert _md_files, "no prompt .md files discovered — path wrong?"
