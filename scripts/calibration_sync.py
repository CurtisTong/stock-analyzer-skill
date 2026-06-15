#!/usr/bin/env python3
"""校准数据 GitHub Gist 双向同步。

用法：
  python3 scripts/calibration_sync.py --pull    # 从 gist 拉取校准数据
  python3 scripts/calibration_sync.py --push    # 推送本地校准数据到 gist
  python3 scripts/calibration_sync.py --auto    # 自动同步（先拉后推）
  python3 scripts/calibration_sync.py --status  # 查看同步状态

需要 gh CLI 已登录（gh auth login）。
Gist 文件名：expert_calibration.json
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CALIBRATION_FILE = _PROJECT_ROOT / "data" / "expert_calibration.json"
_GIST_DESC = "stock-analyzer-skill calibration data"
_GIST_FILENAME = "expert_calibration.json"


def _run_gh(args: list[str], input_data: str | None = None) -> tuple[int, str, str]:
    """运行 gh CLI 命令。"""
    cmd = ["gh"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=input_data,
            timeout=30,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", "gh CLI 未安装。请先安装: brew install gh"
    except subprocess.TimeoutExpired:
        return 1, "", "gh 命令超时"


def _find_gist() -> str | None:
    """查找已存在的校准数据 gist。"""
    code, stdout, stderr = _run_gh(["gist", "list", "--limit", "100", "--json", "id,description,files"])
    if code != 0:
        return None

    try:
        gists = json.loads(stdout)
    except json.JSONDecodeError:
        return None

    for gist in gists:
        desc = gist.get("description", "")
        if _GIST_DESC in desc:
            return gist["id"]
        # 兼容旧描述
        if "calibration" in desc.lower() and "stock" in desc.lower():
            return gist["id"]

    return None


def _get_gist_content(gist_id: str) -> dict | None:
    """从 gist 读取校准数据。"""
    code, stdout, stderr = _run_gh(["gist", "view", gist_id, "--filename", _GIST_FILENAME])
    if code != 0:
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _create_gist(data: dict) -> str | None:
    """创建新 gist。"""
    import tempfile
    content = json.dumps(data, ensure_ascii=False, indent=2)

    # gh gist create 需要文件路径，用临时文件
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp_path = f.name

    try:
        code, stdout, stderr = _run_gh([
            "gist", "create", tmp_path,
            "--desc", _GIST_DESC,
            "--filename", _GIST_FILENAME,
        ])
        if code != 0:
            print(f"❌ 创建 gist 失败: {stderr}", file=sys.stderr)
            return None

        # stdout 格式: https://gist.github.com/xxx/yyy
        gist_url = stdout.strip()
        gist_id = gist_url.split("/")[-1]
        return gist_id
    finally:
        os.unlink(tmp_path)


def _update_gist(gist_id: str, data: dict) -> bool:
    """更新已有 gist。"""
    import tempfile
    content = json.dumps(data, ensure_ascii=False, indent=2)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(content)
        tmp_path = f.name

    try:
        code, stdout, stderr = _run_gh([
            "gist", "edit", gist_id,
            "--filename", _GIST_FILENAME,
            "--file", tmp_path,
        ])
        return code == 0
    finally:
        os.unlink(tmp_path)


def pull() -> bool:
    """从 gist 拉取校准数据到本地。"""
    gist_id = _find_gist()
    if not gist_id:
        print("⚠️  未找到远程校准数据 gist。")
        return False

    remote_data = _get_gist_content(gist_id)
    if not remote_data:
        print("❌ 无法读取远程校准数据。")
        return False

    # 备份本地数据
    if _CALIBRATION_FILE.exists():
        backup = _CALIBRATION_FILE.with_suffix(".json.bak")
        backup.write_text(_CALIBRATION_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"📦 本地数据已备份到 {backup.name}")

    # 写入远程数据
    _CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CALIBRATION_FILE.write_text(
        json.dumps(remote_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    pred_count = len(remote_data.get("predictions", []))
    expert_count = sum(1 for v in remote_data.get("experts", {}).values() if v.get("events", 0) > 0)
    print(f"✅ 拉取成功：{pred_count} 条预测，{expert_count} 位专家有数据")
    return True


def push() -> bool:
    """推送本地校准数据到 gist。"""
    if not _CALIBRATION_FILE.exists():
        print("⚠️  本地无校准数据。")
        return False

    local_data = json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))
    gist_id = _find_gist()

    if gist_id:
        # 更新已有 gist
        if _update_gist(gist_id, local_data):
            print(f"✅ 已更新 gist: {gist_id}")
            return True
        else:
            print("❌ 更新 gist 失败。")
            return False
    else:
        # 创建新 gist
        new_id = _create_gist(local_data)
        if new_id:
            print(f"✅ 已创建 gist: {new_id}")
            return True
        else:
            print("❌ 创建 gist 失败。")
            return False


def auto() -> bool:
    """自动同步：先拉取，再推送（本地数据更多时覆盖远程）。"""
    print("🔄 自动同步...")
    pull()

    if not _CALIBRATION_FILE.exists():
        return False

    local_data = json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))
    local_preds = len(local_data.get("predictions", []))

    gist_id = _find_gist()
    if gist_id:
        remote_data = _get_gist_content(gist_id)
        remote_preds = len(remote_data.get("predictions", [])) if remote_data else 0

        if local_preds >= remote_preds:
            print(f"📤 本地数据更多（{local_preds} vs {remote_preds}），推送到远程...")
            return push()
        else:
            print(f"📥 远程数据更多（{remote_preds} vs {local_preds}），跳过推送。")
            return True
    else:
        print("📤 无远程 gist，创建新的...")
        return push()


def status() -> None:
    """查看同步状态。"""
    print("📊 校准数据同步状态")
    print("=" * 40)

    # 本地状态
    if _CALIBRATION_FILE.exists():
        local_data = json.loads(_CALIBRATION_FILE.read_text(encoding="utf-8"))
        local_preds = len(local_data.get("predictions", []))
        local_verified = sum(1 for p in local_data.get("predictions", []) if p.get("verified"))
        local_experts = sum(1 for v in local_data.get("experts", {}).values() if v.get("events", 0) > 0)
        print(f"本地: {local_preds} 条预测（{local_verified} 已验证），{local_experts} 位专家有数据")
    else:
        print("本地: 无数据")

    # 远程状态
    gist_id = _find_gist()
    if gist_id:
        remote_data = _get_gist_content(gist_id)
        if remote_data:
            remote_preds = len(remote_data.get("predictions", []))
            remote_verified = sum(1 for p in remote_data.get("predictions", []) if p.get("verified"))
            print(f"远程: {remote_preds} 条预测（{remote_verified} 已验证），gist: {gist_id}")
        else:
            print(f"远程: gist {gist_id} 存在但无法读取")
    else:
        print("远程: 无 gist")


def main() -> None:
    parser = argparse.ArgumentParser(description="校准数据 GitHub Gist 双向同步")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pull", action="store_true", help="从 gist 拉取校准数据")
    group.add_argument("--push", action="store_true", help="推送本地校准数据到 gist")
    group.add_argument("--auto", action="store_true", help="自动同步")
    group.add_argument("--status", action="store_true", help="查看同步状态")

    args = parser.parse_args()

    if args.pull:
        pull()
    elif args.push:
        push()
    elif args.auto:
        auto()
    elif args.status:
        status()


if __name__ == "__main__":
    main()
