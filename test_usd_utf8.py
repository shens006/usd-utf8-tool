import tempfile
import unittest
from pathlib import Path

from usd_utf8 import ConversionError, convert, doctor, inspect, repair_escaped_strings

try:
    from pxr import Sdf, Usd
except ImportError:
    Sdf = Usd = None


SCENE = '''#usda 1.0
(
    defaultPrim = "装配"
)
def Xform "装配" (
    displayName = "总装 零件"
    customData = { string 原名 = "设计零件" }
)
{
    custom string 说明 = "中文描述"
    custom token[] 标签 = ["钢材", "机械"]
    rel target = </装配/螺栓>
    def Xform "螺栓" {
        double3 xformOp:translate = (1, 2, 3)
    }
}
'''


class EncodingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, text=SCENE, encoding="gbk", name="model.usda"):
        path = self.root / name
        path.write_bytes(text.encode(encoding))
        return path

    def basic(self, source, **kwargs):
        return convert(source, skip_usd_validation=True, **kwargs)

    def test_gb_family_exact_transcoding(self):
        for encoding in ("gb2312", "gbk", "gb18030"):
            with self.subTest(encoding=encoding):
                source = self.write(encoding=encoding, name=encoding + ".usd")
                before = source.read_bytes()
                result = self.basic(source, encoding=encoding)
                self.assertEqual(Path(result["output"]).read_bytes(), SCENE.encode("utf-8"))
                self.assertEqual(source.read_bytes(), before)

    def test_gb18030_four_byte_character(self):
        source = self.write(SCENE.replace("中文描述", "中文𠀀"), "gb18030")
        result = self.basic(source, encoding="gb18030")
        self.assertIn("𠀀", Path(result["output"]).read_text())

    def test_gbk_trailing_backslash_byte(self):
        char = next(chr(i) for i in range(0x4e00, 0x9fff)
                    if chr(i).encode("gbk", errors="ignore").endswith(b"\\"))
        source = self.write(SCENE.replace("中文描述", char))
        result = self.basic(source, encoding="gbk")
        self.assertIn(char, Path(result["output"]).read_text())

    def test_auto_requires_explicit_non_utf8(self):
        source = self.write()
        with self.assertRaises(ConversionError):
            self.basic(source)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_inspect_preview(self):
        result = inspect(self.write())
        self.assertFalse(result["utf8_valid"])
        self.assertIn("装配", str(result["candidates"]))

    def test_utf8_idempotence_and_bom(self):
        source = self.write(encoding="utf-8-sig")
        one = self.basic(source)
        two = self.basic(Path(one["output"]))
        self.assertEqual(Path(one["output"]).read_bytes(), Path(two["output"]).read_bytes())

    def test_no_overwrites(self):
        source = self.write()
        with self.assertRaises(ConversionError):
            self.basic(source, output=source, encoding="gbk")
        output = self.root / "exists.usda"
        output.write_text("existing")
        with self.assertRaises(ConversionError):
            self.basic(source, output=output, encoding="gbk")
        self.assertEqual(output.read_text(), "existing")

    def test_symlink_output_rejected(self):
        source = self.write()
        output = self.root / "link.usda"
        output.symlink_to(self.root / "missing")
        with self.assertRaises(ConversionError):
            self.basic(source, output=output, encoding="gbk")

    def test_dry_run_no_files(self):
        result = self.basic(self.write(), encoding="gbk", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_lossy_or_invalid_bytes_rejected(self):
        source = self.write(SCENE.replace("中文描述", "�"), "utf-8")
        with self.assertRaises(ConversionError):
            self.basic(source)
        source.write_bytes(b'#usda 1.0\n#\xff\n')
        with self.assertRaises(ConversionError):
            self.basic(source, encoding="gbk")

    def test_unknown_and_package_rejected(self):
        source = self.write()
        for data in (b"not usd", b"PK\x03\x04", b"\x00\x01"):
            source.write_bytes(data)
            with self.assertRaises(ConversionError):
                inspect(source)

    def test_escaped_literals_and_comments(self):
        text = '# comment "\\xd6\\xd0"\n' + r'"literal \\xd6" "\xd6\xd0\xce\xc4"'
        result, count = repair_escaped_strings(text, "gbk")
        self.assertEqual(count, 1)
        self.assertIn('"中文"', result)
        self.assertIn(r'"literal \\xd6"', result)
        self.assertIn('# comment "\\xd6\\xd0"', result)

    def test_escaped_gb_trail_quote_and_backslash(self):
        for char in ("中文", "乗"):
            escaped = "".join("\\x%02x" % b for b in char.encode("gbk"))
            fixed, count = repair_escaped_strings('"' + escaped + '"', "gbk")
            self.assertEqual(fixed, '"' + char + '"')
            self.assertEqual(count, 1)

    def test_cross_directory_rejected(self):
        source = self.write()
        folder = self.root / "other"
        folder.mkdir()
        with self.assertRaises(ConversionError):
            self.basic(source, output=folder / "output.usda", encoding="gbk")

    def test_escaped_repair_preserves_literal_unicode(self):
        for encoding in ("gb2312", "gbk", "gb18030"):
            with self.subTest(encoding=encoding):
                text = '"正常🙂" "🙂\\xd6\\xd0\\xce\\xc4"'
                repaired, count = repair_escaped_strings(text, encoding)
                self.assertEqual(repaired, '"正常🙂" "🙂中文"')
                self.assertEqual(count, 1)

    def test_convert_preserves_utf8_escapes_with_gb_fallback(self):
        source = self.write(
            '#usda 1.0\ndef "Part" {\n'
            ' custom string good = "\\344\\270\\255\\346\\226\\207"\n'
            ' custom string bad = "\\xd6\\xd0\\xce\\xc4"\n}\n', "utf-8")
        result = self.basic(source, escaped_encoding="gbk")
        content = Path(result["output"]).read_text(encoding="utf-8")
        self.assertIn('good = "中文"', content)
        self.assertIn('bad = "中文"', content)

    @unittest.skipUnless(Sdf, "requires usd-core")
    def test_usd_semantics(self):
        result = convert(self.write(), encoding="gbk")
        stage = Usd.Stage.Open(result["output"])
        prim = stage.GetPrimAtPath("/装配")
        self.assertEqual(stage.GetDefaultPrim(), prim)
        self.assertEqual(prim.GetDisplayName(), "总装 零件")
        self.assertEqual(prim.GetCustomDataByKey("原名"), "设计零件")
        self.assertEqual(prim.GetAttribute("说明").Get(), "中文描述")
        self.assertEqual(str(prim.GetRelationship("target").GetTargets()[0]), "/装配/螺栓")
        self.assertEqual(tuple(stage.GetPrimAtPath("/装配/螺栓").GetAttribute("xformOp:translate").Get()), (1, 2, 3))

    @unittest.skipUnless(Sdf, "requires usd-core")
    def test_parse_failure_does_not_write(self):
        source = self.write('#usda 1.0\ndef Xform "中文 名称" {}\n')
        with self.assertRaises(ConversionError):
            convert(source, encoding="gbk")
        self.assertEqual(len(list(self.root.iterdir())), 1)

    @unittest.skipUnless(Sdf, "requires usd-core")
    def test_crate_roundtrip(self):
        source = self.write()
        result = convert(source, output=self.root / "binary.usdc", encoding="gbk")
        crate = Path(result["output"])
        self.assertTrue(crate.read_bytes().startswith(b"PXR-USDC"))
        self.assertTrue(inspect(crate)["utf8_valid"])
        result = convert(crate, output=self.root / "back.usda")
        stage = Usd.Stage.Open(result["output"])
        self.assertEqual(stage.GetPrimAtPath("/装配").GetAttribute("说明").Get(), "中文描述")

    @unittest.skipUnless(Sdf, "requires usd-core")
    def test_real_crate_with_invalid_gb_metadata(self):
        layer = Sdf.Layer.CreateAnonymous()
        prim = Sdf.PrimSpec(layer, "Part", Sdf.SpecifierDef)
        prim.SetInfo("displayName", "中文零件".encode("gbk"))
        source = self.root / "invalid.usdc"
        layer.Export(str(source))
        before = source.read_bytes()
        report = inspect(source)
        self.assertTrue(report["utf8_valid"])
        self.assertFalse(report["utf8_strings_valid"])
        with self.assertRaises(ConversionError):
            convert(source)
        result = convert(source, encoding="gbk")
        stage = Usd.Stage.Open(result["output"])
        self.assertEqual(stage.GetPrimAtPath("/Part").GetDisplayName(), "中文零件")
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(result["repaired_escaped_strings"], 1)

    @unittest.skipUnless(Sdf, "requires usd-core")
    def test_external_reference_preserved(self):
        scene = '#usda 1.0\n( subLayers = [@子层.usda@] )\ndef Xform "Root" {}\n'
        source = self.write(scene)
        result = convert(source, encoding="gbk")
        self.assertEqual(result["external_assets"], ["子层.usda"])
        self.assertEqual(Path(result["output"]).read_text(), scene)

    @unittest.skipUnless(Sdf, "requires usd-core")
    def test_doctor(self):
        self.assertTrue(doctor()["chinese_prim_parse"])


if __name__ == "__main__":
    unittest.main()
