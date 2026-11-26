"""Track keyboard activity across prompts in one unlocked session."""

import asyncio
import time
from contextlib import contextmanager


IDLE_SECONDS = 5 * 60
_deadline = None


class IdleLock(Exception):
    """The unlocked session exceeded its inactivity limit."""


@contextmanager
def watch_session():
    global _deadline
    _deadline = time.monotonic() + IDLE_SECONDS
    try:
        yield
    finally:
        _deadline = None


def ask(prompt):
    if _deadline is None:
        return prompt.unsafe_ask()
    if time.monotonic() >= _deadline:
        raise IdleLock()

    app = prompt.application

    def record_key(_):
        global _deadline
        now = time.monotonic()
        if now < _deadline:
            _deadline = now + IDLE_SECONDS

    async def lock_when_idle():
        while not app.is_done:
            remaining = _deadline - time.monotonic()
            if remaining <= 0:
                app.exit(exception=IdleLock())
                return
            await asyncio.sleep(remaining)

    app.key_processor.before_key_press += record_key
    try:
        answer = app.run(pre_run=lambda: app.create_background_task(lock_when_idle()))
        if time.monotonic() >= _deadline:
            raise IdleLock()
        return answer
    finally:
        app.key_processor.before_key_press -= record_key
