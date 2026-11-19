"""Stage 'remedies': stub written by F2. The owner of this stage replaces this file.

Contract: def run(ctx) -> None (engine/context.py RunContext). Read with ctx.table / ctx.read,
write with ctx.write. Remove NOT_IMPLEMENTED when the real stage is in place.
"""
from __future__ import annotations

NOT_IMPLEMENTED = True


def run(ctx) -> None:
    """Log that the stage is not built yet; the run records it as skipped."""
    ctx.log.info("stage remedies: not implemented yet")
