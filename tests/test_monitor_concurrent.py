"""NotificationManager 并发安全测试。"""

import threading
from monitor.manager import NotificationManager


def test_concurrent_throttle_check():
    """多线程并发 _check_throttle 不应抛异常。"""
    nm = NotificationManager()
    errors = []

    def check(i):
        try:
            nm._check_throttle("test_source")
            with nm._lock:
                nm._daily_count += 1
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=check, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0, f"并发错误: {errors}"
