"""Offline runtime checks and actionable installation instructions; stdlib only."""
import importlib.util
import platform
import shlex
import struct
import subprocess
import sys


def command(parts, windows=None):
    windows = sys.platform == "win32" if windows is None else windows
    return ("& " + subprocess.list2cmdline(parts)) if windows else shlex.join(parts)


def installation_steps():
    windows = sys.platform == "win32"
    python = ["py", "-3.12"] if windows else ["python3.12"]
    local = ".venv\\Scripts\\python.exe" if windows else ".venv/bin/python"
    return [
        "没有 Python：从 https://www.python.org/downloads/ 安装 64 位 CPython 3.12（或受支持的 3.10–3.14）。",
        "以下命令在解压后的工具目录执行，创建独立环境：",
        command(python + ["-m", "venv", ".venv"], windows),
        command([local, "-m", "pip", "install", "--upgrade", "pip"], windows),
        command([local, "-m", "pip", "install", "."], windows),
        "如果 pip 缺失：用该环境的 Python 执行 -m ensurepip --upgrade。",
        "如果 Linux 缺少 venv/ensurepip：安装发行版对应的 python3-venv 或 python3.12-venv 包。",
        "若提示 No matching distribution：检查 Python 版本、64 位架构和 usd-core wheel 是否支持该平台。",
        "若提示代理/TLS/超时：检查网络和 pip 源；不要用关闭 TLS 校验的方式处理。",
    ]


def dependency_hint():
    if sys.prefix != sys.base_prefix and "omni.kit.app" not in sys.modules:
        return command([sys.executable, "-m", "pip", "install", "--upgrade", "usd-core>=24.3"])
    return "请在工具目录创建独立 .venv 并执行 python -m pip install .；运行 usd-utf8 doctor 查看完整步骤。"


def runtime_report():
    report = {
        "python": platform.python_version(), "executable": sys.executable,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(), "architecture": platform.machine(),
        "bits": struct.calcsize("P") * 8,
        "virtual_environment": sys.prefix != sys.base_prefix,
        "minimum_unicode_identifiers": "24.03", "checks": [],
        "installation": installation_steps(),
    }
    checks = report["checks"]
    def add(name, ok, detail, required=True):
        checks.append({"name": name, "status": "ok" if ok else "error" if required else "warning",
                       "detail": detail})
    add("Python", (3, 10) <= sys.version_info[:2] < (3, 15), "要求 Python 3.10–3.14，推荐 3.12。")
    add("64-bit", report["bits"] == 64, "OpenUSD 预编译包需要匹配的 64 位 Python。")
    add("pip", importlib.util.find_spec("pip") is not None,
        "缺少时执行 python -m ensurepip --upgrade；已装 SDK 的运行不依赖 pip。", False)
    add("venv", importlib.util.find_spec("venv") is not None,
        "用于创建独立环境；Linux 可安装发行版提供的 venv 包。", False)
    try:
        from pxr import Sdf, Usd
        version = tuple(Usd.GetVersion())
        report["usd_version"] = list(version)
        add("OpenUSD", version >= (0, 24, 3), "需要 OpenUSD >=24.03。当前：" + ".".join(map(str, version)))
        report["chinese_identifier"] = bool(Sdf.Path.IsValidIdentifier("中文零件"))
        layer = Sdf.Layer.CreateAnonymous("probe.usda")
        report["chinese_prim_parse"] = bool(layer.ImportFromString('#usda 1.0\ndef Xform "中文零件" {}\n'))
        add("UTF-8 Prim", report["chinese_identifier"] and report["chinese_prim_parse"],
            "验证中文标识符与匿名层解析；不检查 Kit 字体。")
    except Exception as exc:
        try:
            detail = str(exc)
        except Exception:
            detail = type(exc).__name__
        add("OpenUSD import/probe", False, detail + "\n安装或更新：" + dependency_hint())
    report["ready"] = all(c["status"] != "error" for c in checks)
    if not report["ready"]:
        report["error"] = "运行环境未就绪，请按 installation 安装后重新运行 doctor。"
    report["note"] = "扫描工具不需要 GPU、Isaac Sim 或 Kit；本检查不代表目标 Kit UI 的字体支持。"
    return report
