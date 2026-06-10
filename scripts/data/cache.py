"""缓存模块兼容层。

v1.3.1 起，缓存实现已迁移到 common.cache（避免 common ↔ data 循环依赖）。
此模块保留作为 shim，确保 `from data import cache` 旧调用方式继续可用。
"""
# 让 data.cache 实际指向 common.cache 模块本身，避免 "common.cache is not data.cache"
# 注意：必须放在文件最前面，且后续不能定义同名符号，否则会破坏 is 关系。
import common.cache as _cache

# 重新绑定当前模块的"身份"为 common.cache
import sys
sys.modules[__name__] = _cache
