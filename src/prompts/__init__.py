"""Prompt loader: reads .md templates from this directory and substitutes {placeholders}."""
import os
from string import Template

_DIR = os.path.dirname(os.path.abspath(__file__))


def load_prompt(_prompt_name: str, /, **kwargs) -> str:
    """Load `<_prompt_name>.md` from this directory and substitute ${var} placeholders.

    Uses string.Template ($var / ${var}) instead of str.format so that JSON braces
    and curly braces in the prompt body don't need to be escaped. The first arg is
    positional-only so callers can pass a template variable named `name` via kwargs.
    """
    path = os.path.join(_DIR, f"{_prompt_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        body = f.read()
    return Template(body).safe_substitute(**kwargs)
