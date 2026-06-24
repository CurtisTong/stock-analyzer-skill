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
    parser.add_argument(
        "-j", "--json", action="store_true", dest="json_output", help="JSON 格式输出"
    )
    parser.add_argument("--sources", action="store_true", help="显示可用数据源")
    parser.add_argument(
        "--no-cache", action="store_true", help="禁用缓存，强制实时获取"
    )
    return parser


@contextmanager
def handle_errors():
    """统一错误处理上下文管理器。

    捕获异常并输出中文友好消息，替代各脚本的 try/except 模式。
    """
    try:
        yield
    except KeyboardInterrupt:
        print("\n⏹ 已中断", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        from common.exceptions import format_error

        print(f"❌ {format_error(e)}", file=sys.stderr)
        sys.exit(1)


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
