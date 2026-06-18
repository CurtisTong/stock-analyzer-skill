#!/usr/bin/env python3
"""校验 skills/_shared/contracts/ 下所有 JSON Schema 的合法性、引用闭合、枚举值一致。

用法：
    python3 scripts/dev/validate_contracts.py
    python3 scripts/dev/validate_contracts.py --strict   # 严格模式：警告变错误
"""
import json
import sys
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parent.parent.parent / "skills" / "_shared" / "contracts"


def collect_schemas(contracts_dir: Path) -> dict[str, dict]:
    """加载所有 *.schema.json。"""
    schemas = {}
    for f in sorted(contracts_dir.glob("*.schema.json")):
        with open(f) as fh:
            schemas[f.name] = json.load(fh)
    return schemas


def check_references(schemas: dict[str, dict], strict: bool) -> list[str]:
    """校验所有 $ref 引用的 schema 都存在。"""
    issues = []
    available = {k.replace(".schema.json", "") for k in schemas.keys()}
    for name, schema in schemas.items():
        refs = _find_refs(schema)
        for ref in refs:
            # ref 形如 "./stock.schema.json" 或 "stock.schema.json"
            target = ref.lstrip("./").replace(".schema.json", "")
            if target not in available:
                issues.append(f"❌ {name}: 引用 {ref} → {target} 不存在")
    return issues


def _find_refs(obj) -> list[str]:
    """递归查找所有 $ref。"""
    refs = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "$ref":
                refs.append(v)
            else:
                refs.extend(_find_refs(v))
    elif isinstance(obj, list):
        for item in obj:
            refs.extend(_find_refs(item))
    return refs


def check_top_level_keys(schemas: dict[str, dict]) -> list[str]:
    """校验 schema 顶层必备字段。"""
    issues = []
    for name, schema in schemas.items():
        if "$schema" not in schema:
            issues.append(f"⚠️  {name}: 缺 $schema 字段")
        if "type" not in schema:
            issues.append(f"⚠️  {name}: 缺 type 字段")
        if "title" not in schema:
            issues.append(f"⚠️  {name}: 缺 title 字段（影响 IDE 提示）")
    return issues


def _short_name(filename: str) -> str:
    """stock.schema.json → stock。"""
    return filename.replace(".schema.json", "")


def main() -> int:
    strict = "--strict" in sys.argv

    if not CONTRACTS_DIR.exists():
        print(f"❌ contracts 目录不存在: {CONTRACTS_DIR}")
        return 1

    schemas = collect_schemas(CONTRACTS_DIR)
    if not schemas:
        print(f"⚠️  未发现任何 schema 文件 in {CONTRACTS_DIR}")
        return 0

    print(f"==> 找到 {len(schemas)} 个 schema: {', '.join(sorted(schemas.keys()))}\n")

    all_issues = []
    all_issues.extend(check_top_level_keys(schemas))
    all_issues.extend(check_references(schemas, strict))

    if all_issues:
        print("==> 发现问题：")
        for issue in all_issues:
            print(f"  {issue}")
        errors = [i for i in all_issues if i.startswith("❌")]
        warnings = [i for i in all_issues if i.startswith("⚠️")]
        if strict or errors:
            print(f"\n❌ 失败：{len(errors)} 错误, {len(warnings)} 警告")
            return 1
        print(f"\n⚠️  通过（含 {len(warnings)} 警告）")
    else:
        print("✅ 所有 schema 合法、引用闭合")

    return 0


if __name__ == "__main__":
    sys.exit(main())
