"""Prompt loader: reads .md templates from this directory and substitutes {placeholders}."""
import os
import re
from functools import lru_cache
from string import Template

_DIR = os.path.dirname(os.path.abspath(__file__))
_BLANK_RUN = re.compile(r"\n{3,}")


@lru_cache(maxsize=None)
def _read_template(prompt_name: str) -> Template:
    path = os.path.join(_DIR, f"{prompt_name}.md")
    with open(path, "r", encoding="utf-8") as f:
        return Template(f.read())


def load_prompt(_prompt_name: str, /, **kwargs) -> str:
    """Load `<_prompt_name>.md` from this directory and substitute ${var} placeholders.

    Uses string.Template ($var / ${var}) instead of str.format so that JSON braces
    and curly braces in the prompt body don't need to be escaped. The first arg is
    positional-only so callers can pass a template variable named `name` via kwargs.
    Templates are cached after first read; runs of 3+ newlines (left over when a
    conditional fragment is empty) collapse to a single blank line.

    Missing kwargs raise KeyError — pass empty strings explicitly for fragments
    that should be omitted, so typos and forgotten variables fail loudly.
    """
    rendered = _read_template(_prompt_name).substitute(**kwargs)
    return _BLANK_RUN.sub("\n\n", rendered)
