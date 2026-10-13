"""Console entry point. Check Python before importing the implementation."""
import json
import sys

VERSION = "0.2.0"


def render(result):
    if "checks" in result:
        print("USD UTF-8 环境检查")
        print("Python: {} ({})".format(result["python"], result["executable"]))
        print("平台: {} / {} 位".format(result["platform"], result["bits"]))
        for check in result["checks"]:
            print("[{}] {}: {}".format(check["status"].upper(), check["name"], check["detail"]))
        print("\n" + ("环境就绪。" if result["ready"] else "环境未就绪。安装步骤："))
        if not result["ready"]:
            for step in result["installation"]:
                print(step)
        print(result["note"])
    elif "summary" in result:
        print("扫描目录: " + result["root"])
        print("USD 文件: {}，工程体积: {:.1f} MiB".format(result["usd_files"], result["project_bytes"] / 1024 ** 2))
        for item in result["files"]:
            print("[{}] {}{}".format(item["status"], item["file"],
                                      " — " + item["reason"] if "reason" in item else ""))
        print("统计: " + ", ".join("{}={}".format(k, v) for k, v in result["summary"].items()))
        for link in result["symlinks"]:
            print("[review] 符号链接: " + link)
        if result["output"]:
            print("修复副本: " + result["output"])
            print("详细报告: " + result["output"] + "/_usd_utf8_scan.json")
        if "open_in_kit" in result:
            print("Kit 入口（相对于副本）: " + result["open_in_kit"])
        if not result["complete"]:
            print("仍有未处理项目，请查看报告。")
        print("检查范围为编码和单层 USD 解析；字体、二次乱码和场景运行需另行确认。")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Avoid Windows console failures on non-ASCII diagnostic messages.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    if argv == ["--version"]:
        print("usd-utf8 " + VERSION)
        return 0
    if not (3, 10) <= sys.version_info[:2] < (3, 15):
        message = "需要 Python 3.10–3.14，推荐安装 64 位 Python 3.12：https://www.python.org/downloads/"
        print(json.dumps({"error": message}, ensure_ascii=False) if "--json" in argv else message, file=sys.stderr)
        return 2
    from usd_utf8 import main as run
    return run(argv, human=True)


if __name__ == "__main__":
    sys.exit(main())
