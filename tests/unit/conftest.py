"""tests/unit/ 子目录的 conftest。

顶层 conftest 已按目录自动打 unit marker，本文件放 unit 层专属 fixture。
"""

import socket

import pytest

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


@pytest.fixture(autouse=True)
def _no_outbound_network(monkeypatch):
    """单元测试禁止访问外网（v1.33.0）。

    背景：event 因子（balanced 权重 0.05）与基准 K 线获取会在打分/回测路径
    直连东财，本地有缓存时看不出问题，CI 出网受限时表现为 pytest-timeout
    60s 的偶发红灯（2026-11-08 py3.12/3.13 实测三处）。

    localhost 放行，允许 portfolio-web 等本地 HTTP 测试；外网一律抛错，
    让"偷偷连网"的测试立刻失败并指向根因，而不是偶发超时。
    """
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host in _LOCAL_HOSTS:
            return real_connect(self, address)
        raise OSError(f"单元测试禁止访问外网: {host}（需要网络交互请 mock 掉数据源）")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
