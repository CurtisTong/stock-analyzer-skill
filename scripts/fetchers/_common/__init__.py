"""_common：fetcher 内部共享辅助模块（非数据域）。

pytdx_pool 通过显式路径 import（from fetchers._common.pytdx_pool import ...），
此处不做 re-export，避免在 pytdx 未安装时预加载导致 HAS_PYTDX 被缓存为 False。
"""
