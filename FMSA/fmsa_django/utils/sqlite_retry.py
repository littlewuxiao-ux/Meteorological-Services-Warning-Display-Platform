"""生产库并发写入时，SQLite 锁住就等一会儿再写。"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

from django.db import OperationalError, connections, transaction

logger = logging.getLogger('fmsa.db')
T = TypeVar('T')


def retry_if_locked(action: Callable[[], T], *, using: str = 'runtime', attempts: int = 8) -> T:
    delay = 0.15
    last: OperationalError | None = None
    for index in range(attempts):
        try:
            with transaction.atomic(using=using):
                return action()
        except OperationalError as exc:
            text = str(exc).lower()
            if 'locked' not in text and 'busy' not in text:
                raise
            last = exc
            logger.warning('数据库忙，第 %s 次重试（%s）', index + 1, using)
            try:
                connections[using].close()
            except Exception:
                pass
            time.sleep(delay)
            delay = min(delay * 2, 2.0)
    assert last is not None
    raise last
