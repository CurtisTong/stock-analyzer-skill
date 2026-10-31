"""CLI 脚本公共参数和错误处理基座。

提供统一的 argparse 配置，确保所有 CLI 脚本有一致的参数风格：
  -j / --json    JSON 输出
  --sources      显示可用数据源
  --no-cache     禁用缓存

用法:
    from common.cli_base import create_parser, handle_errors

    parser = create_parser(description="实时行情查询")
    parser.add_argument("codes", nargs="+")  # 脚本自有参数
    args = parser.parse_args()

    with handle_errors():
        main(args)
"""

import argparse
import os
import sys
from contextlib import contextmanager


def create_parser(description: str, **kwargs) -> argparse.ArgumentParser:
    """创建带公共参数的 argparse.ArgumentParser。

    Args:
        description: 脚本描述
        **kwargs: 传递给 ArgumentParser 的额外参数

    Returns:
        配置好公共参数的 parser
    """
    parser = argparse.ArgumentParser(description=description, **kwargs)
    parser.add_argument("-j", "--json", action="store_true", dest="json_output", help="JSON 格式输出")
    parser.add_argument("--sources", action="store_true", help="显示可用数据源")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存，强制实时获取")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="调试模式：异常时打印完整 traceback（设 STOCK_DEBUG=1 等效）",
    )
    return parser


@contextmanager
def handle_errors():
    """统一错误处理上下文管理器。

    捕获异常并输出中文友好消息，替代各脚本的 try/except 模式。
    当 STOCK_DEBUG 环境变量为 1 时（或 --debug 在 parse 前设置该变量），
    打印完整 traceback 以便定位根因，而非仅输出通用提示。
    """
    debug = os.environ.get("STOCK_DEBUG", "") == "1"
    try:
        yield
    except KeyboardInterrupt:
        print("\n⏹ 已中断", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        # v1.20.1: ScreenerTimeoutError 已在 _run_main 内处理(打印 + sys.exit(2)),
        # 此处仅兜底未被业务捕获的 TimeoutError（一般是 inner socket 15s）。
        from common.exceptions import ScreenerTimeoutError

        if isinstance(e, ScreenerTimeoutError):
            print(f"\n⚠️ {e.message}", file=sys.stderr)
            sys.exit(2)
        if debug:
            import traceback

            traceback.print_exc()
        else:
            print(sandwich_error(e), file=sys.stderr)
        sys.exit(1)


# 错误"三明治"结构（user_expert §3.3）：[症状 | 根因 | 下一步]。
# 每个异常类型给"下一步该做什么"，而不是只扔一行消息。
_SANDWICH_HINTS = {
    "NetworkError": (
        "数据源请求失败（交易所限频或本地网络断开）",
        [
            "① 等 60 秒再试（限频多数会自动恢复）",
            "② 用 /screener init default 走离线预置数据",
            "③ 仍失败 → 提交 issue 并附 --debug 输出",
        ],
    ),
    "RateLimitError": (
        "请求频率超过数据源限制",
        ["① 等 60 秒再试", "② 减少 --codes 数量或分批跑", "③ 数据为缓存时可加 --no-cache 跳过"],
    ),
    "ValidationError": (
        "输入未通过校验（代码格式/日期格式）",
        [
            "① 股票代码支持 sh600989 / 600989 / 贵州茅台 三种写法",
            "② 日期用 2024-01-01 格式",
            "③ 不确定代码时用 /screener 或 /market 找标的",
        ],
    ),
    "InsufficientDataError": (
        "数据不足，无法生成完整分析（K 线/财务缺失）",
        ["① 换全市场大票试（小票数据源覆盖少）", "② 数据源恢复后重试", "③ /stock-help 查看可用命令"],
    ),
    "ScreenerTimeoutError": (
        "选股超时——标的多或数据源慢",
        [
            "① 减少候选池（--codes 或 --top）",
            "② 用 --no-regime / --no-macro 跳过重计算",
            "③ 重跑一次（首轮缓存暖身后通常更快）",
        ],
    ),
}


def sandwich_error(error: Exception) -> str:
    """把异常格式化为 [❌ 消息 / 症状 / 根因 / 下一步] 三明治结构。"""
    from common.exceptions import format_error

    lines = [f"❌ {format_error(error)}"]
    hint = None
    for cls in type(error).__mro__:
        if cls.__name__ in _SANDWICH_HINTS:
            hint = _SANDWICH_HINTS[cls.__name__]
            break
    if hint:
        reason, actions = hint
        lines.append(f"【根因】{reason}")
        lines.append("【下一步】" + " ".join(actions))
    else:
        lines.append("【下一步】加 --debug 或设 STOCK_DEBUG=1 可查看完整 traceback 并上报")
    return "\n".join(lines)


def print_sources_table(domains: dict) -> None:
    """打印数据源可用性表格。

    Args:
        domains: {domain_name: [fetcher, ...]} 结构
    """
    for domain, fetchers in domains.items():
        print(f"=== {domain} 数据源 ===")
        print(f"{'名称':<25} {'优先级':>6} {'状态':<8}")
        print("-" * 45)
        for f in fetchers:
            status = "✅" if f.is_available() else "❌"
            print(f"  {f.name:<23} {f.priority:>6} {status:<8}")
        print()
