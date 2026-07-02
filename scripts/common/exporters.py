"""数据导出与风险提示。"""

from __future__ import annotations
from pathlib import Path
from typing import List

RISK_DISCLAIMER = """
⚠️ 风险提示
- 本分析仅供参考，不构成投资建议
- 股市有风险，投资需谨慎
- 历史表现不代表未来收益
- 请根据自身风险承受能力做出决策
"""


def add_risk_disclaimer(text: str) -> str:
    """添加风险提示。"""
    return text + RISK_DISCLAIMER


def export_to_csv(data: List[dict], filename: str, output_dir: str = "output") -> str:
    """导出数据到 CSV 文件。"""
    import csv
    import re

    # P3: 清洗 filename，防止路径遍历（../）和非法字符
    filename = re.sub(r"[^\w一-龥.-]", "_", filename) or "export"

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    filepath = output_path / f"{filename}.csv"

    if not data:
        filepath.write_text("", encoding="utf-8-sig")
        return str(filepath)

    fieldnames = list(data[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    return str(filepath)


def export_analysis_to_csv(analysis: dict, filename: str) -> str:
    """导出分析结果到 CSV。"""
    flat_data = _flatten_dict(analysis)
    data = [{"指标": k, "值": v} for k, v in flat_data.items()]
    return export_to_csv(data, filename)


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """扁平化嵌套字典。"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep).items())
        elif isinstance(v, list):
            items.append((new_key, str(v)))
        else:
            items.append((new_key, v))
    return dict(items)
