"""Is this a full source checkout, or the subset the Docker image carries?

**Shared because the same mistake has now been made twice.** Both times a test
asserted something about the *repository* — a manifest covering every measurement
document, an error message matching `CLAUDE.md` — and both times it passed
locally and turned the Docker job red, because the runtime image is deliberately
a partial checkout.

The image copies `src/`, `tests/` and `scripts/` in full, but only the parts of
`docs/` it needs at runtime, and no `CLAUDE.md` at all (Dockerfile). A test that
reads a developer-facing document is therefore not *weaker* in the image, it is
**meaningless** — the thing it asserts about is legitimately absent.

Not a module in ``tests/conftest.py`` because ``pytest.mark.skipif`` needs a
module-level value at import time, which a fixture cannot provide.

## Choosing a sentinel

Both sentinels below are large, permanent, developer-facing files with no
runtime role, so neither will ever be added to the image "by accident". Prefer
the one your test actually depends on — a test that reads `CLAUDE.md` should
skip on `CLAUDE_MD_PRESENT`, not on a proxy, so that the skip reason stays true
if the Dockerfile's `docs/` allowlist changes.
"""

from pathlib import Path

__all__ = [
    "CLAUDE_MD_PRESENT",
    "FULL_DOCS_CHECKOUT",
    "PARTIAL_CHECKOUT_REASON",
    "REPO_ROOT",
]

REPO_ROOT = Path(__file__).resolve().parents[1]

FULL_DOCS_CHECKOUT = (REPO_ROOT / "docs" / "DECISIONS.md").is_file()
"""Is the whole `docs/` tree present? False in the Docker image."""

CLAUDE_MD_PRESENT = (REPO_ROOT / "CLAUDE.md").is_file()
"""Is `CLAUDE.md` present? False in the Docker image, which never copies it."""

PARTIAL_CHECKOUT_REASON = (
    "needs a full source checkout; the Docker image copies only part of docs/ and "
    "no CLAUDE.md, so this asserts repository structure that is legitimately "
    "absent there"
)
