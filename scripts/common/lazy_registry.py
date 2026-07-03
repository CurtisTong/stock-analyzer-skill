"""延迟加载与缓存的 fetcher 注册表。

线程安全双重检查锁（DCL）的通用实现，消除 chip/event/flow/lhb 四个
数据域中复制粘贴的 _fetchers_cache / _fetchers_lock / _get_*_fetchers /
_find_fetcher 模板代码。

用法:
    _registry = LazyFetcherRegistry(get_chip_fetchers)
    fetchers = _registry.get_all()
    margin_fetcher = _registry.find("margin")

仅测试用:
    _registry.reset()  # 清除缓存，下次 get_all() 重新加载
"""

import threading
from typing import Callable, Optional


class LazyFetcherRegistry:
    """线程安全的延迟加载 fetcher 注册表。

    采用双重检查锁（DCL）模式：第一次 get_all() 调用时触发导入和缓存，
    后续调用直接返回缓存列表。find() 通过 name 前缀匹配查找单个 fetcher。
    """

    def __init__(self, import_func: Callable[[], list]):
        """初始化注册表。

        Args:
            import_func: 无参函数，调用后返回 fetcher 对象列表。
                         典型用法是传入 fetchers 模块的 get_xxx_fetchers 函数。
        """
        self._import_func = import_func
        self._cache: Optional[list] = None
        self._lock = threading.Lock()

    def get_all(self) -> list:
        """返回缓存的 fetcher 列表，首次调用时触发延迟加载。

        Returns:
            fetcher 对象列表（来自 import_func 的返回值）。
        """
        if self._cache is not None:
            return self._cache
        with self._lock:
            if self._cache is not None:
                return self._cache
            self._cache = self._import_func()
        return self._cache

    def find(self, name_prefix: str):
        """按 name 前缀查找单个 fetcher。

        Args:
            name_prefix: fetcher.name 的前缀字符串，如 "margin"。

        Returns:
            第一个 name.startswith(name_prefix) 的 fetcher，未找到返回 None。
        """
        for f in self.get_all():
            if f.name.startswith(name_prefix):
                return f
        return None

    def reset(self):
        """重置缓存，仅用于测试隔离。

        调用后下次 get_all() 将重新执行 import_func。
        """
        with self._lock:
            self._cache = None
