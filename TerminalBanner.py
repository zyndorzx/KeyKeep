"""Animated ASCII title for Key Keeper's entry menus."""

import asyncio
import os
import sys
import time

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, FormattedTextControl, HSplit, Layout, Window

from SessionActivity import ask


_SMALL_LETTERS = {
    "K": ("## ##", "#### ", "###  ", "#### ", "## ##"),
    "E": ("#####", "##   ", "#### ", "##   ", "#####"),
    "Y": ("## ##", "#####", " ### ", " ### ", " ### "),
    "P": ("#### ", "## ##", "#### ", "##   ", "##   "),
    "R": ("#### ", "## ##", "#### ", "## ##", "## ##"),
}
_LARGE_LETTERS = {
    "K": ("###  ##", "### ## ", "#####  ", "####   ", "#####  ", "### ## ", "###  ##", "###  ##"),
    "E": ("#######", "#######", "###    ", "###### ", "###### ", "###    ", "#######", "#######"),
    "Y": ("### ###", "### ###", " ##### ", "  ###  ", "  ###  ", "  ###  ", "  ###  ", "  ###  "),
    "P": ("###### ", "#######", "###  ##", "#######", "###### ", "###    ", "###    ", "###    "),
    "R": ("###### ", "#######", "###  ##", "#######", "###### ", "### ## ", "###  ##", "###  ##"),
}
_TITLE = "KEY KEEPER"


def _wordmark(letters, height):
    return tuple(
        "    ".join(" ".join(letters[letter][row] for letter in word) for word in _TITLE.split())
        for row in range(height)
    )


_LARGE_ART = _wordmark(_LARGE_LETTERS, 8)
_SMALL_ART = _wordmark(_SMALL_LETTERS, 5)
_INK = ("#4c6585", "#506893", "#586598", "#626298", "#6b5f8e", "#685e83", "#5a607f", "#50617d")
_FRAME_TIME = 0.10
_EXIT_TIME = 0.36


def _render_banner(columns, lines, elapsed, departure=0):
    # Keep the title clear of the final column to avoid an automatic line wrap.
    width = max(1, columns - 1)
    if width >= len(_LARGE_ART[0]) and lines >= 18:
        title = _LARGE_ART
    elif width >= len(_SMALL_ART[0]) and lines >= 14:
        title = _SMALL_ART
    else:
        title = (_TITLE[:width],)

    left = min((columns - len(title[0])) // 2, width - len(title[0]))
    fragments = [("", "\n")] if lines >= 18 else []
    for y, row in enumerate(title):
        fragments.append(("", " " * left))
        for x, character in enumerate(row):
            edge = 1 - departure - (x / len(row) * 0.77 + y / len(title) * 0.23)
            if character == " " or edge <= 0:
                fragments.append(("", " "))
                continue
            shade = int((x * 0.08 + y * 0.11 - elapsed * 3) % len(_INK))
            fragments.append((f"fg:{_INK[shade]} bold", character))
        if y < len(title) - 1 or lines >= 14:
            fragments.append(("", "\n"))
    return fragments


def _banner(started, *, leaving=False):
    exit_started = time.monotonic()

    def draw():
        size = get_app().output.get_size()
        now = time.monotonic()
        return _render_banner(
            size.columns, size.rows, now - started,
            departure=(now - exit_started) / _EXIT_TIME if leaving else 0,
        )

    return Window(FormattedTextControl(draw), wrap_lines=False, dont_extend_height=True)


def _centered_screen(*contents):
    """Keep a startup prompt in the visual center of the terminal."""
    spacer = lambda: Window(height=Dimension(weight=1))
    return HSplit([spacer(), *contents, spacer()])


def _animate_out(started):
    bindings = KeyBindings()

    @bindings.add("c-c", eager=True)
    @bindings.add("c-q", eager=True)
    def cancel(event):
        event.app.exit(exception=KeyboardInterrupt())

    @bindings.add("<any>")
    def ignore_key(event):
        pass

    transition = Application(
        layout=Layout(_centered_screen(_banner(started, leaving=True))),
        key_bindings=bindings,
        refresh_interval=_FRAME_TIME / 2,
        erase_when_done=True,
    )

    async def finish():
        await asyncio.sleep(_EXIT_TIME)
        transition.exit()

    transition.run(pre_run=lambda: transition.create_background_task(finish()))


def ask_banner_menu(prompt):
    """Show the title above a Questionary menu and animate it away on selection."""
    if (
        not (sys.stdin.isatty() and sys.stdout.isatty())
        or os.environ.get("TERM") == "dumb"
        or os.environ.get("NO_COLOR")
        or os.environ.get("KEYKEEP_NO_ANIMATION")
    ):
        return ask(prompt)

    app = prompt.application
    started = time.monotonic()
    app.layout.container = _centered_screen(_banner(started), app.layout.container)
    app.refresh_interval = _FRAME_TIME
    answer = ask(prompt)
    _animate_out(started)
    return answer
