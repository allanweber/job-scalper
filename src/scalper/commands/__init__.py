"""Front-end-agnostic command layer (Phase 6).

Each module exposes a single entry function (``run_collect`` / ``run_report`` /
``run_sources`` / ``run_status``) that takes plain typed params and returns a typed
result object. The **purity contract**: the command layer has no ``argparse``, no
``print``/direct stderr, no ``sys.exit``, and no browser-opening. It raises
exceptions instead of exiting, and streams progress through injected callbacks
(default no-op) so a CLI prints it while a future web/desktop/mobile app can stream
it differently. The CLI (``scalper.cli``) owns all printing, exit codes, and the
browser launch.
"""

from __future__ import annotations


class CommandError(Exception):
    """A user-facing failure raised by the command layer.

    The CLI maps it to an ``error: …`` line on stderr and exit code 1, instead of
    the command itself printing or calling ``sys.exit``.
    """
