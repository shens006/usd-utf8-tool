"""Recursive project scanner. Repairs a separate project copy, never the source."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from usd_utf8 import (ConversionError, ENCODINGS, convert, error_text, preview,
                      read_layer, repair_escaped_strings, sdk, validate)

USD_SUFFIXES = {".usd", ".usda", ".usdc", ".usdz"}
IGNORED = {".git", ".venv", "__pycache__"}
REPORT_NAME = "_usd_utf8_scan.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def choose_encoding(data, encoding="auto-gb"):
    """UTF-8 first; within the user-selected GB family, require identical results."""
    utf8_text = None
    try:
        utf8_text = data.decode("utf-8")
        text, escaped = repair_escaped_strings(utf8_text, "utf-8")
        return text, "utf-8", escaped, ["utf-8"], None
    except (UnicodeError, ConversionError):
        pass
    possibilities = []
    for codec in ENCODINGS[1:] if encoding == "auto-gb" else (encoding,):
        try:
            # A crate may export good Unicode literally and bad bytes as escapes.
            # Preserve the valid Unicode instead of decoding the whole export as GB.
            base = utf8_text if utf8_text is not None else data.decode(codec)
            text, escaped = repair_escaped_strings(base, codec)
            possibilities.append((text, codec, escaped))
        except (UnicodeError, ConversionError):
            pass
    if not possibilities:
        raise ConversionError("不能按 UTF-8 或选定 GB 编码严格解码；需人工检查。")
    if len({x[0] for x in possibilities}) != 1:
        raise ConversionError("GB 候选产生不同文字，无法自动选择；请指定来源编码。")
    text, codec, escaped = possibilities[0]
    return (text, "utf-8" if utf8_text is not None else codec, escaped,
            [x[1] for x in possibilities], codec if utf8_text is not None else None)


def display_audit(layer):
    Sdf, _ = sdk()
    findings = []

    def visit(path):
        obj = layer.GetObjectAtPath(path)
        if not isinstance(obj, Sdf.PrimSpec):
            return
        name = str(obj.name)
        display = obj.GetInfo("displayName") if obj.HasInfo("displayName") else ""
        if display or any(ord(char) > 127 for char in name):
            if len(findings) < 100:
                findings.append({"path": str(path), "displayName": display,
                                 "unicode_prim_name": any(ord(c) > 127 for c in name),
                                 "note": "已有显示名；在 Stage 开启显示名并检查字体。" if display else
                                 "真实 Prim 名称含非 ASCII；保留原路径，不自动改名。"})

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return findings


def analyze_file(path, relative, encoding):
    item = {"file": str(relative)}
    try:
        item["source_sha256"] = sha(path.read_bytes())
        if path.suffix.lower() == ".usdz":
            item.update(status="unsupported", reason="USDZ 需解包；保留原文件，不自动修复。")
            return item
        raw, data, kind = read_layer(path)
        if sha(raw) != item["source_sha256"]:
            raise ConversionError("文件在扫描时变化，请重试。")
        text, codec, escaped, candidates, escaped_codec = choose_encoding(data, encoding)
        if "\ufffd" in text or "\x00" in text:
            raise ConversionError("发现已有 � 或 NUL；不猜测丢失的文字。")
        layer, checked = validate(text)
        changed = codec != "utf-8" or escaped > 0 or raw.startswith(b"\xef\xbb\xbf")
        item.update(status="repairable" if changed else "ok", format=kind,
                    encoding=codec, compatible_encodings=candidates,
                    escaped_encoding=escaped_codec,
                    escaped_strings=escaped, preview=preview(text),
                    display_names=display_audit(layer), **checked)
    except Exception as exc:
        item.update(status="review", reason=error_text(exc))
    return item


def inventory(root):
    files, links = [], []
    def onerror(exc):
        raise exc
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=onerror):
        base = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in IGNORED)
        for name in list(dirs):
            if (base / name).is_symlink():
                links.append(base / name)
                dirs.remove(name)
        for name in sorted(names):
            path = base / name
            if path.is_symlink():
                links.append(path)
            elif path.is_file():
                files.append(path)
            else:
                raise ConversionError("工程含非常规文件，无法制作副本：" + str(path))
    return files, links


def create_label_overlay(project, entry, labels):
    """Optional labels use explicit path->name mappings; never infer lost names."""
    Sdf, Usd = sdk()
    source = project / entry
    stage = Usd.Stage.Open(str(source), load=Usd.Stage.LoadNone)
    if not stage:
        raise ConversionError("无法打开显示名覆盖层入口。")
    target = source.with_name(source.stem + ".chinese.usda")
    if target.exists():
        raise ConversionError("显示名覆盖层文件已存在：" + str(target))
    layer = Sdf.Layer.CreateAnonymous("labels.usda")
    layer.subLayerPaths = ["./" + source.name]
    # Preserve authored root-stage metadata, without copying the entry's sublayers.
    for key in stage.GetRootLayer().pseudoRoot.ListInfoKeys():
        if key not in ("subLayers", "subLayerOffsets"):
            layer.pseudoRoot.SetInfo(key, stage.GetRootLayer().pseudoRoot.GetInfo(key))
    for path_text, label in labels.items():
        path = Sdf.Path(path_text)
        if (not path.IsAbsolutePath() or not path.IsPrimPath()
                or path.ContainsPrimVariantSelection()):
            raise ConversionError("显示名映射必须是绝对 Prim 路径：" + path_text)
        prim = stage.GetPrimAtPath(path)
        if not prim or prim.IsInstanceProxy():
            raise ConversionError("显示名目标不存在、在未加载 payload 内或为实例代理：" + path_text)
        if not isinstance(label, str) or not label.strip() or "\ufffd" in label or "\0" in label:
            raise ConversionError("显示名必须是非空、无损的文字：" + path_text)
        Sdf.CreatePrimInLayer(layer, path).SetInfo("displayName", label)
    if not layer.Export(str(target)):
        raise ConversionError("显示名覆盖层导出失败。")
    composed = Usd.Stage.Open(str(target), load=Usd.Stage.LoadNone)
    for path, label in labels.items():
        if not composed or composed.GetPrimAtPath(path).GetDisplayName() != label:
            raise ConversionError("显示名覆盖层验证失败：" + path)
    return str(target.relative_to(project))


def scan(root, fix=False, output=None, encoding="auto-gb", entry=None, labels=None):
    sdk()  # Scanning must not silently claim USD validity without a parser.
    root = root.resolve()
    if not root.is_dir():
        raise ConversionError("scan 输入必须是工程目录。")
    if encoding not in ("auto-gb", "gb2312", "gbk", "gb18030"):
        raise ConversionError("未知来源编码。")
    output = (output or root.with_name(root.name + ".utf8")).absolute()
    if fix and (output.resolve() == root or root in output.resolve().parents):
        raise ConversionError("修复副本必须在扫描目录之外。")
    if fix and (output.exists() or output.is_symlink()):
        raise ConversionError("副本目录已存在，不会覆盖：" + str(output))
    if (entry is None) != (labels is None):
        raise ConversionError("--entry 和 --labels 需同时提供。")
    label_map = None
    if entry is not None:
        entry_path = (root / entry).resolve()
        if not entry_path.is_relative_to(root) or not entry_path.is_file():
            raise ConversionError("--entry 必须指向扫描目录内的 USD 文件。")
        entry = entry_path.relative_to(root)
        try:
            label_map = json.loads(labels.read_text(encoding="utf-8-sig"))
        except (ValueError, UnicodeError) as exc:
            raise ConversionError("显示名 JSON 无法读取：" + error_text(exc)) from exc
        if not isinstance(label_map, dict) or not label_map:
            raise ConversionError("--labels 应是非空 JSON 对象：Prim 路径 → 中文显示名。")
    files, links = inventory(root)
    usd_files = [p for p in files if p.suffix.lower() in USD_SUFFIXES]
    items = [analyze_file(p, p.relative_to(root), encoding) for p in usd_files]
    counts = Counter(x["status"] for x in items)
    result = {"root": str(root), "output": str(output) if fix else None,
              "mode": "fix" if fix else "scan", "summary": dict(counts),
              "usd_files": len(items), "project_files": len(files),
              "project_bytes": sum(p.stat().st_size for p in files),
              "symlinks": [str(p.relative_to(root)) for p in links],
              "files": items, "complete": False,
              "notes": ["auto-gb 假设来源属于 UTF-8/GB 系列；GB 候选必须产生完全相同的文字才自动修复。",
                        "有效 UTF-8 的二次乱码不能可靠自动识别；不自动改名 Prim、关节或资源文件。",
                        "字体与 Stage 显示设置需在 Isaac Sim/Kit 中检查；文件扫描不能验证 UI 字形。",
                        "工程副本保留目录和文件名；绝对路径、目录外引用及自定义 resolver 不会重定向。"]}
    if not fix:
        result["complete"] = not (counts["review"] or counts["unsupported"] or links)
        return result
    if not items:
        raise ConversionError("没有找到 USD 文件，不生成工程副本。")
    if links:
        raise ConversionError("工程包含符号链接；请先整理独立工程副本，避免引用原目录：" +
                              ", ".join(result["symlinks"][:8]))
    if any(p.relative_to(root) == Path(REPORT_NAME) for p in files):
        raise ConversionError("输入已有扫描报告，请移走或重命名后再生成新副本。")
    if not output.parent.is_dir():
        raise ConversionError("副本的父目录不存在。")
    # Work privately. Claim output with mkdir only after repairs finish; no overwrite.
    with tempfile.TemporaryDirectory(prefix=".usd-project-", dir=output.parent) as directory:
        project = Path(directory) / "project"
        shutil.copytree(root, project, symlinks=True,
                        ignore=shutil.ignore_patterns(*IGNORED))
        snapshot_files, snapshot_links = inventory(project)
        if snapshot_links or {p.relative_to(project) for p in snapshot_files} != {
                p.relative_to(root) for p in files}:
            raise ConversionError("工程文件列表在扫描后发生变化，请重新扫描。")
        for item in items:
            path = project / item["file"]
            if sha(path.read_bytes()) != item.get("source_sha256"):
                raise ConversionError("文件在扫描后变化：" + item["file"])
            if item["status"] != "repairable":
                continue
            # Temporary output is in the same directory, preserving relative anchoring.
            with tempfile.TemporaryDirectory(prefix=".repair-", dir=path.parent) as work:
                converted = Path(work) / path.name
                report = convert(path, output=converted, encoding=item["encoding"],
                                 escaped_encoding=item["escaped_encoding"],
                                 allow_relocation=True)
                os.replace(converted, path)  # Only the private copy is replaced.
            item.update(status="fixed", output_sha256=report["output_sha256"])
        if label_map is not None:
            if any(x["status"] in ("review", "unsupported") for x in items):
                raise ConversionError("还有未修复 USD，不能验证显示名覆盖层；先解决报告中的问题。")
            result["open_in_kit"] = create_label_overlay(project, entry, label_map)
        result["summary"] = dict(Counter(x["status"] for x in items))
        result["complete"] = not any(x["status"] in ("review", "unsupported") for x in items)
        result["notes"].append("review/unsupported 文件原样保留；complete=false 表示仍需人工处理。")
        (project / REPORT_NAME).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        output.mkdir()  # Exclusive; refuses a concurrently created destination.
        try:
            for child in project.iterdir():
                shutil.move(str(child), str(output / child.name))
        except Exception:
            # We own this newly created directory. Do not leave a partial project.
            shutil.rmtree(output)
            raise
    return result
