#!/usr/bin/env python3
"""Strict, non-destructive single-layer USD encoding inspection and conversion."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ENCODINGS = ("utf-8", "gb2312", "gbk", "gb18030")


class ConversionError(Exception):
    pass


def error_text(exc):
    try:
        return str(exc)
    except Exception:
        return type(exc).__name__ + "（SDK 错误消息本身含非法 UTF-8）"


def repair_escaped_strings(text, encoding):
    """Decode USD-exported byte escapes inside quoted literals only.

    Skip comments and asset literals. Honor escaped backslashes so a literal
    string such as \\xd6 is not mistaken for a byte escape. Preserve literal
    Unicode and prefer UTF-8 for each string before trying the selected codec.
    """
    parts, count, i = [], 0, 0
    escapes = {"n": b"\n", "r": b"\r", "t": b"\t", "b": b"\b",
               "f": b"\f", "v": b"\v", "a": b"\a", "\\": b"\\",
               '"': b'"', "'": b"'"}
    while i < len(text):
        start = i
        if text[i] == "#":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end + 1
        elif text[i] == "@":
            delimiter = "@@@" if text.startswith("@@@", i) else "@"
            end = text.find(delimiter, i + len(delimiter))
            i = len(text) if end < 0 else end + len(delimiter)
        elif text[i] in "\"'":
            quote = text[i]
            delimiter = quote * (3 if text.startswith(quote * 3, i) else 1)
            i += len(delimiter)
            decoded = bytearray()
            segments = []
            high_byte = False
            closed = False
            while i < len(text):
                if text.startswith(delimiter, i):
                    i += len(delimiter)
                    closed = True
                    break
                if text[i] == "\\" and i + 1 < len(text):
                    match = re.match(r"\\x([0-9a-fA-F]{2})|\\([0-7]{1,3})", text[i:i + 4])
                    if match:
                        value = int(match[1], 16) if match[1] else int(match[2], 8)
                        if value > 255:
                            raise ConversionError("字符串八进制转义超过一个字节。")
                        decoded.append(value)
                        high_byte |= value >= 128
                        i += len(match[0])
                        continue
                    pair = text[i:i + 2]
                    if pair[1] in escapes:
                        decoded.extend(escapes[pair[1]])
                    elif pair.isascii():
                        decoded.extend(pair.encode("ascii"))
                    else:
                        segments.extend((bytes(decoded), pair))
                        decoded.clear()
                    i += 2
                else:
                    if text[i].isascii():
                        decoded.append(ord(text[i]))
                    else:
                        segments.extend((bytes(decoded), text[i]))
                        decoded.clear()
                    i += 1
            if high_byte:
                if not closed:
                    raise ConversionError("含转义字节的字符串未闭合。")
                segments.append(bytes(decoded))
                def decode_segments(codec):
                    return "".join(part.decode(codec, errors="strict")
                                   if isinstance(part, bytes) else part
                                   for part in segments)
                try:
                    value = decode_segments("utf-8")
                except UnicodeError:
                    try:
                        value = decode_segments(encoding)
                    except UnicodeError as exc:
                        raise ConversionError("字符串转义字节不能按所选编码解码：" + error_text(exc)) from exc
                value = value.replace("\\", "\\\\").replace(quote, "\\" + quote)
                for character, escape in (("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t"),
                                          ("\b", "\\b"), ("\f", "\\f"), ("\v", "\\v"),
                                          ("\a", "\\a"), ("\0", "\\x00")):
                    value = value.replace(character, escape)
                parts.append(delimiter + value + delimiter)
                count += 1
                continue
        else:
            i += 1
        parts.append(text[start:i])
    return "".join(parts), count


def sdk():
    try:
        from pxr import Sdf, Usd
    except (ImportError, OSError) as exc:
        from usd_env import dependency_hint
        raise ConversionError(
            "OpenUSD Python SDK 无法加载。安装或修复：" + dependency_hint() +
            "；运行 usd-utf8 doctor 查看环境和安装步骤。原因：" + error_text(exc)
        ) from exc
    if tuple(Usd.GetVersion()) < (0, 24, 3):
        from usd_env import dependency_hint
        raise ConversionError("需要 OpenUSD >=24.03。" + dependency_hint())
    return Sdf, Usd


def doctor():
    from usd_env import runtime_report
    return runtime_report()


def read_layer(path: Path):
    raw = path.read_bytes()
    if raw.startswith(b"PXR-USDC"):
        Sdf, _ = sdk()
        try:
            # Do not decode the crate. Let USD export the layer without flattening.
            layer = Sdf.Layer.OpenAsAnonymous(str(path.resolve()))
            if not layer:
                raise ConversionError("OpenUSD 无法读取此 USDC。")
            with tempfile.TemporaryDirectory(prefix="usd-encoding-") as directory:
                exported = Path(directory) / "source.usda"
                if not layer.Export(str(exported)):
                    raise ConversionError("USDC 导出 USDA 失败。")
                data = exported.read_bytes()
        except Exception as exc:
            raise ConversionError(
                "USDC 无法无损导出文本层；请从原始设计软件重新导出 USDA。原因：" + error_text(exc)
            ) from exc
        return raw, data, "usdc"
    if raw.startswith(b"PK") or path.suffix.lower() == ".usdz":
        raise ConversionError("USDZ 是打包容器，本工具不直接转换；请先用 USD 工具解包。")
    data = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    if not data.startswith(b"#usda 1.0"):
        raise ConversionError("未识别为 USDA 或 USDC；不根据 .usd 扩展名猜测格式。")
    return raw, data, "usda"


def preview(text: str):
    result = []
    for number, line in enumerate(text.splitlines(), 1):
        if any(ord(c) > 127 for c in line):
            result.append({"line": number, "text": line[:240]})
        if len(result) >= 16:
            break
    return result


def candidates(data: bytes):
    results = []
    for encoding in ENCODINGS:
        try:
            text = data.decode(encoding, errors="strict")
            repaired, escaped = repair_escaped_strings(text, encoding)
            results.append({"encoding": encoding, "decodes": True,
                            "roundtrip": text.encode(encoding) == data,
                            "escaped_strings": escaped, "preview": preview(repaired)})
        except (UnicodeError, ConversionError) as exc:
            results.append({"encoding": encoding, "decodes": False, "error": error_text(exc)})
    return results


def inspect(path: Path):
    raw, data, kind = read_layer(path)
    options = candidates(data)
    try:
        data.decode("utf-8", errors="strict")
        utf8 = True
    except UnicodeError:
        utf8 = False
    return {
        "source": str(path.resolve()), "format": kind, "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "utf8_valid": utf8, "utf8_strings_valid": options[0]["decodes"], "candidates": options,
        "note": ("字节已是有效 UTF-8；若仍乱码，请检查字体、displayName 或二次误解码。"
                 if utf8 and options[0]["decodes"] else
                 "原始字节或字符串转义内容不是 UTF-8；对照预览后显式指定 --encoding。"),
        "binary_note": ("候选编码针对 SDK 导出的 USDA，不是对二进制容器解码。"
                        if kind == "usdc" else None),
    }


def validate(text: str):
    Sdf, Usd = sdk()
    try:
        layer = Sdf.Layer.CreateAnonymous("validate.usda")
        if not layer.ImportFromString(text):
            raise ConversionError("USD 解析失败。")
        # This tests the layer, not the composed stage; do not load dependencies.
        refs = sorted(layer.GetExternalReferences())
        return layer, {"usd_version": list(Usd.GetVersion()),
                       "usd_validation": "passed (single layer, not composed stage)",
                       "external_assets": refs}
    except Exception as exc:
        raise ConversionError("转码后 USD 解析失败，未写输出：" + error_text(exc)) from exc


def decode(data: bytes, encoding: str):
    if encoding == "auto":
        try:
            return data.decode("utf-8", errors="strict"), "utf-8"
        except UnicodeError as exc:
            names = [x["encoding"] for x in candidates(data) if x["decodes"]]
            raise ConversionError(
                "不是有效 UTF-8。请先 inspect 并指定 --encoding gbk/gb2312/gb18030。"
                " 可严格解码候选：" + ", ".join(names)
            ) from exc
    try:
        return data.decode(encoding, errors="strict"), encoding
    except UnicodeError as exc:
        raise ConversionError("严格解码失败（未替换或丢弃任何字节）：" + str(exc)) from exc


def convert(source: Path, output: Path | None = None, encoding="auto",
            dry_run=False, skip_usd_validation=False, allow_replacement=False,
            allow_relocation=False, escaped_encoding=None):
    source = source.resolve()
    raw, data, kind = read_layer(source)
    output = (output or source.with_name(source.stem + ".utf8" + source.suffix)).absolute()
    if output.resolve() == source:
        raise ConversionError("输出不能覆盖原文件。")
    if output.exists() or output.is_symlink():
        raise ConversionError("输出已存在，请使用新的文件名：" + str(output))
    if output.suffix.lower() not in (".usd", ".usda", ".usdc"):
        raise ConversionError("输出扩展名必须是 .usd、.usda 或 .usdc。")
    if output.parent.resolve() != source.parent and not allow_relocation:
        raise ConversionError(
            "跨目录保存会改变相对引用基准；请同目录输出，或显式 --allow-relocation 并自行维护资源。")
    text, selected = decode(data, encoding)
    text, escaped_strings = repair_escaped_strings(text, escaped_encoding or selected)
    if "\x00" in text:
        raise ConversionError("文本包含 NUL，不是可安全转码的 USDA。")
    if "\ufffd" in text and not allow_replacement:
        raise ConversionError(
            "发现已有替换字符 �，原始字符可能已丢失；本工具无法恢复。"
            "若只需保留它并转码其余内容，可显式 --allow-replacement。")
    encoded = text.encode("utf-8", errors="strict")
    warnings = ["仅转换当前 layer；不会自动转换 sublayer/reference/payload，"
                "不会重命名磁盘资源或重写其他文件中指向本层的路径。"]
    if selected != "utf-8":
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeError:
            pass
        else:
            warnings.append("输入同时也是有效 UTF-8；你显式选择了 GB 编码，请核对预览避免二次乱码。")
    if "\ufffd" in text:
        warnings.append("输出保留已有 �；不代表损坏文字已恢复。")
    if output.parent.resolve() != source.parent:
        warnings.append("输出位置改变，相对资源解析需要人工核对。")
    binary_output = output.suffix.lower() == ".usdc" or (
        output.suffix.lower() == ".usd" and kind == "usdc")
    layer = None
    validation = {"usd_validation": "skipped; only strict encoding checked"}
    if skip_usd_validation:
        if kind == "usdc" or binary_output:
            raise ConversionError("二进制输入或输出不可跳过 USD 验证。")
    else:
        layer, validation = validate(text)
    result = {"source": str(source), "output": str(output),
              "input_format": kind, "output_format": "usdc" if binary_output else "usda",
              "selected_encoding": selected, "dry_run": dry_run,
              "escaped_encoding": escaped_encoding or selected,
              "repaired_escaped_strings": escaped_strings,
              "source_sha256": hashlib.sha256(raw).hexdigest(),
              "preview": preview(text), "warnings": warnings, **validation}
    if dry_run:
        return result
    if not output.parent.is_dir():
        raise ConversionError("输出目录不存在。")
    # Stage the complete output, validate it, then create the destination exclusively.
    # os.link is atomic and refuses overwrites, including symlinks and concurrent writes.
    fd, name = tempfile.mkstemp(prefix=".usd-utf8-", suffix=".usdc" if binary_output else ".usda",
                                dir=str(output.parent))
    os.close(fd)
    temporary = Path(name)
    try:
        if binary_output:
            if not layer.Export(str(temporary)):
                raise ConversionError("USDC 写入失败。")
            Sdf, _ = sdk()
            check = Sdf.Layer.OpenAsAnonymous(str(temporary))
            if not check or check.ExportToString() != layer.ExportToString():
                raise ConversionError("USDC 往返校验失败，未发布输出。")
        else:
            temporary.write_bytes(encoded)
        # Detect changes while conversion was in progress, including the binary export.
        if source.read_bytes() != raw:
            raise ConversionError("转换期间原文件发生变化，请重试。")
        result["output_sha256"] = hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    result["written"] = True
    return result


def main(argv=None, human=False):
    parser = argparse.ArgumentParser(description="USD 中文编码检测与严格 UTF-8 转换（不覆盖原文件）")
    parser.add_argument("--version", action="version", version="usd-utf8 0.2.0")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="测试当前 Python 的 OpenUSD 中文 Prim 支持")
    p = sub.add_parser("scan", help="递归扫描工程；--fix 在独立工程副本内修复")
    p.add_argument("root", type=Path)
    p.add_argument("--fix", action="store_true", help="生成修复副本，保留原工程")
    p.add_argument("-o", "--output", type=Path, help="副本目录；默认原目录名加 .utf8")
    p.add_argument("--encoding", choices=("auto-gb", "gb2312", "gbk", "gb18030"), default="auto-gb")
    p.add_argument("--entry", type=Path, help="显示名覆盖层所引用的工程内入口 USD")
    p.add_argument("--labels", type=Path, help="JSON 映射：绝对 Prim 路径 → 中文显示名")
    p = sub.add_parser("inspect", help="检测真实格式并显示各编码中文预览")
    p.add_argument("source", type=Path)
    p = sub.add_parser("convert", help="转换单个 layer；默认使用 SDK 验证")
    p.add_argument("source", type=Path)
    p.add_argument("-o", "--output", type=Path)
    p.add_argument("--encoding", choices=("auto",) + ENCODINGS, default="auto")
    p.add_argument("--escaped-encoding", choices=ENCODINGS[1:], help="仅修复字符串转义字节时使用的 GB 编码")
    p.add_argument("--dry-run", action="store_true", help="只预览和验证，不写文件")
    p.add_argument("--skip-usd-validation", action="store_true", help="仅文本；显式跳过 SDK 解析")
    p.add_argument("--allow-replacement", action="store_true", help="保留已有 �（不能恢复它）")
    p.add_argument("--allow-relocation", action="store_true", help="允许跨目录输出，自行维护相对引用")
    for command_parser in sub.choices.values():
        command_parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)
    json_output = args.json or not human
    try:
        if args.command == "doctor":
            result = doctor()
        elif args.command == "inspect":
            result = inspect(args.source)
        elif args.command == "scan":
            from usd_scan import scan
            fields = vars(args).copy()
            fields.pop("command")
            fields.pop("json")
            result = scan(**fields)
        else:
            fields = vars(args).copy()
            fields.pop("command")
            fields.pop("json")
            result = convert(**fields)
        if json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            from usd_cli import render
            render(result)
        return 1 if "error" in result or (args.command == "scan" and not result["complete"]) else 0
    except (ConversionError, OSError, UnicodeError) as exc:
        message = error_text(exc)
        print(json.dumps({"error": message}, ensure_ascii=False) if json_output else "错误：" + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    # scan imports this module too; share classes when launched as a script.
    sys.modules.setdefault("usd_utf8", sys.modules[__name__])
    raise SystemExit(main())
