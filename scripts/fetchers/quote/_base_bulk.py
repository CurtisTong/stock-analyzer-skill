"""全量行情 fetcher 公共基类。

抽取 akshare/efinance 等"拉全市场行情 DataFrame 后行查找"模式的 quote fetcher
公共逻辑，消除两者（120/109 行）的结构重复：

- 缓存 dict + lock + TTL + _loading 标志的 double-checked locking
  （锁内只检查缓存有效性，锁外做网络 IO，避免全市场拉取期间阻塞并发线程）
- 行查找（O(1) 索引优先，回退线性扫描）
- 字段映射 + 异常保护（re-raise 网络异常，其余 return None）

子类只需实现差异部分：
- _sdk_available():  SDK 是否已安装（按 HAS_XXX 标志）
- _fetch_bulk_df():  调用 SDK 拉全量行情 DataFrame（锁外网络 IO）
- _code_column():    代码列名（行查找用）
- _name_column():    名称列名
- _source():         source 字段值
- _index_column():   可选 hook，返回用于 set_index 的列名（None 表示不索引化）

fetcher 为工厂缓存单例（fetchers/__init__.py 的 _fetcher_cache），
故实例级缓存与原模块级缓存在进程生命周期内行为一致。
"""

import logging
import threading
import time
from typing import Any

from common import BaseFetcher, plain_code
from common.exceptions import (
    HTTPStatusError,
    NetworkError,
    ParseError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class BaseBulkQuoteFetcher(BaseFetcher):
    """全量行情 fetcher 基类：封装缓存 + double-checked locking + 字段映射。

    子类只需实现差异部分（SDK 调用、列名、字段映射、source）。
    """

    # 全量行情缓存 TTL（秒）：同一次运行内只拉一次全市场行情
    _cache_ttl = 60

    def __init__(self, name: str, priority: int, provider: str | None = None):
        super().__init__(name, priority=priority, provider=provider)
        # _loading 标志用于 double-checked locking：锁内只检查缓存有效性，
        # 锁外做网络 IO，避免全市场拉取（数秒）期间阻塞所有并发线程。
        self._cache: dict[str, Any] = {"df": None, "ts": 0, "_loading": False}
        self._cache_lock = threading.Lock()

    # ---- 子类必须实现的差异部分 ----

    def _sdk_available(self) -> bool:
        """SDK 是否已安装（默认 True，子类按 HAS_XXX 标志覆盖）。"""
        return True

    def _fetch_bulk_df(self):
        """调用 SDK 拉取全市场行情 DataFrame（锁外网络 IO，耗时数秒）。"""
        raise NotImplementedError

    def _code_column(self) -> str:
        """代码列名（行查找用），如 "代码" / "股票代码"。"""
        raise NotImplementedError

    def _name_column(self) -> str:
        """名称列名，如 "名称" / "股票名称"。"""
        raise NotImplementedError

    def _source(self) -> str:
        """source 字段值。"""
        raise NotImplementedError

    def _index_column(self) -> str | None:
        """用于 set_index 优化的列名；返回 None 表示不做索引化。

        akshare 以"代码"为索引实现 O(1) 查找；efinance 不索引化（线性扫描）。
        """
        return None

    # ---- 字段映射（子类可整体覆盖） ----

    def _build_quote_dict(self, row) -> dict:
        """单行 DataFrame -> 标准行情 dict。

        两个子类（akshare/efinance）字段映射结构完全一致，仅 code/name 列名
        与 source 不同，故在基类统一实现，子类通过 _code_column/_name_column/
        _source 提供差异。如需特殊映射可整体覆盖本方法。
        """
        return {
            "code": str(row.get(self._code_column(), "")),
            "name": str(row.get(self._name_column(), "")),
            "price": str(row.get("最新价", 0)),
            "prev_close": str(row.get("昨收", 0)),
            "open": str(row.get("今开", 0)),
            "change_pct": str(row.get("涨跌幅", 0)),
            "change_amt": str(row.get("涨跌额", 0)),
            "high": str(row.get("最高", 0)),
            "low": str(row.get("最低", 0)),
            "volume": str(row.get("成交量", 0)),
            "amount": str(row.get("成交额", 0)),
            "turnover": str(row.get("换手率", 0)),
            "pe": str(row.get("市盈率-动态", 0)),
            "pe_type": "dynamic",  # 市盈率-动态
            "pb": str(row.get("市净率", 0)),
            "total_cap": str(row.get("总市值", 0)),  # 原始元值，归一化在 data 层
            "circulating_cap": str(row.get("流通市值", 0)),
            "source": self._source(),
        }

    # ---- 模板方法 ----

    def fetch(self, code: str, **kwargs) -> dict | None:
        if not self._sdk_available():
            return None
        try:
            plain = plain_code(code)
            df = self._get_cached_df()
            if df is None:
                return None
            r = self._find_row(df, plain)
            if r is None:
                return None
            return self._build_quote_dict(r)
        except (NetworkError, RateLimitError, HTTPStatusError, ParseError):
            raise  # 网络/限速/解析异常向上抛，触发熔断和退避
        except Exception as e:
            logger.debug("%s 获取失败 %s: %s", self.name, code, e)
            return None

    def _get_cached_df(self):
        """double-checked locking 获取缓存的全量行情 DataFrame。

        P1-2: 锁内只检查缓存，锁外做网络 IO。
        - 缓存有效 -> 直接返回
        - 其他线程正在加载（_loading=True）-> 返回 None（不阻塞等待，让
          manager 切到下一源）
        - 本线程负责加载 -> 锁外网络 IO，成功后写回缓存
        - 加载失败（异常/空 df）-> 清除 _loading 标志（异常则向上抛）

        Returns:
            缓存有效的 DataFrame，或 None（其他线程加载中 / 加载结果为空）
        """
        need_load = False
        with self._cache_lock:
            now = time.time()
            cached_df = self._cache["df"]
            if cached_df is not None and (now - self._cache["ts"] < self._cache_ttl):
                df = cached_df
            elif self._cache["_loading"]:
                # 其他线程正在锁外加载全量行情，本线程不等待，
                # 返回 None 让 manager 切换到下一数据源。
                return None
            else:
                self._cache["_loading"] = True
                need_load = True

        if not need_load:
            return df

        # 锁外网络 IO：拉取全市场行情（数千行，耗时数秒）
        try:
            df = self._fetch_bulk_df()
        except Exception:
            # 任何异常（含 NetworkError 等可熔断异常）：清除 loading 标志后
            # 向上抛，由外层 except 决定是触发熔断还是记录后返回 None。
            with self._cache_lock:
                self._cache["_loading"] = False
            raise
        if df is None or df.empty:
            with self._cache_lock:
                self._cache["_loading"] = False
            return None

        # 可选 hook：以代码列为索引，避免每次 fetch O(n) 线性扫描（P2-15）
        index_col = self._index_column()
        if index_col is not None and index_col in df.columns:
            df = df.set_index(index_col)

        with self._cache_lock:
            self._cache["df"] = df
            self._cache["ts"] = time.time()
            self._cache["_loading"] = False
        return df

    def _find_row(self, df, plain: str):
        """在缓存 DataFrame 中查找指定代码行。

        O(1) 索引查找优先（若已索引化），否则回退 O(n) 线性扫描。
        找不到返回 None。

        注：set_index 后原代码列不再是常规列，索引化路径下 row.get(代码列)
        返回默认值""，与重构前行为一致。
        """
        index_col = self._index_column()
        if index_col is not None and df.index.name == index_col:
            try:
                r = df.loc[plain]
                if r is None or (hasattr(r, "empty") and r.empty):
                    return None
                return r
            except KeyError:
                return None
        # 回退线性扫描
        code_col = self._code_column()
        row_df = df[df[code_col] == plain]
        if row_df.empty:
            return None
        return row_df.iloc[0]
