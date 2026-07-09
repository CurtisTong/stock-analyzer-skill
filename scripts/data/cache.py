"""缓存模块兼容层。

v1.3.1 起，缓存实现已迁移到 common.cache（避免 common ↔ data 循环依赖）。
此模块保留作为兼容入口，确保 `from data import cache` 或
`from data.cache import cache_get` 等旧调用方式继续可用。

P2-24: 移除了 `sys.modules[__name__] = _cache` 的模块身份替换 hack，
改为正常的 re-export。注意 `data.cache` 与 `common.cache` 不再是同一模块对象，
直接 patch `data.cache.CACHE_DIR` 不会影响 `common.cache.CACHE_DIR`--
应 patch `common.cache.CACHE_DIR`（缓存函数实际读取的变量）。
"""

from common.cache import *  # noqa: F401, F403  -- 兼容性 re-export
from common.cache import (
    CACHE_DIR,
    cache_get,
    cache_key,
    cache_key_for_stock,
    cache_cleanup,
    cache_set,
    cleanup,
    cleanup_by_size,
    cleanup_tmp_files,
    get,
    get_cache_stats,
    get_json,
    put,
    set,
    set_json,
)
