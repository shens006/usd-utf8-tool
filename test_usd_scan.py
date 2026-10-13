import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from usd_utf8 import ConversionError
from usd_scan import choose_encoding, scan

try:
    from pxr import Sdf, Usd
except ImportError:
    Sdf = Usd = None


@unittest.skipUnless(Sdf, "requires usd-core")
class ProjectScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        (self.root / "layers").mkdir()
        (self.root / "textures").mkdir()
        (self.root / "textures" / "texture.bin").write_bytes(b"texture\x00\xff")
        (self.root / "scene.usda").write_text(
            '#usda 1.0\n( defaultPrim = "World"\n subLayers = [@layers/parts.usda@] )\n'
            'def Xform "World" {}\n', encoding="utf-8")
        (self.root / "layers" / "parts.usda").write_bytes(
            ('#usda 1.0\nover "World" {\n'
             'def Xform "Part_001" (displayName = "机械臂底座") {\n'
             ' custom asset texture = @../textures/texture.bin@\n'
             ' rel target = </World/Part_002>\n}\n'
             'def Xform "Part_002" {}\n}\n').encode("gbk"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_readonly_and_fix_complete_project(self):
        original = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        report = scan(self.root)
        self.assertEqual(report["summary"], {"ok": 1, "repairable": 1})
        self.assertFalse((self.base / "project.utf8").exists())
        report = scan(self.root, fix=True)
        output = Path(report["output"])
        self.assertEqual(report["summary"], {"ok": 1, "fixed": 1})
        self.assertTrue(report["complete"])
        for rel, data in original.items():
            self.assertEqual((self.root / rel).read_bytes(), data)
        self.assertEqual((output / "scene.usda").read_bytes(), original[Path("scene.usda")])
        self.assertEqual((output / "textures/texture.bin").read_bytes(), b"texture\x00\xff")
        stage = Usd.Stage.Open(str(output / "scene.usda"))
        prim = stage.GetPrimAtPath("/World/Part_001")
        self.assertEqual(prim.GetDisplayName(), "机械臂底座")
        self.assertEqual(str(prim.GetRelationship("target").GetTargets()[0]), "/World/Part_002")
        self.assertEqual(Path(prim.GetAttribute("texture").Get().resolvedPath).resolve(),
                         (output / "textures/texture.bin").resolve())

    def test_mixed_valid_unicode_and_escaped_gb_crate(self):
        layer = Sdf.Layer.CreateAnonymous()
        bad = Sdf.PrimSpec(layer, "Bad", Sdf.SpecifierDef)
        bad.SetInfo("displayName", "中文零件".encode("gbk"))
        good = Sdf.PrimSpec(layer, "Good", Sdf.SpecifierDef)
        good.SetInfo("displayName", "正常文字🙂")
        source = self.root / "mixed.usdc"
        layer.Export(str(source))
        result = scan(self.root, fix=True)
        stage = Usd.Stage.Open(str(Path(result["output"]) / source.name))
        self.assertEqual(stage.GetPrimAtPath("/Good").GetDisplayName(), "正常文字🙂")
        self.assertEqual(stage.GetPrimAtPath("/Bad").GetDisplayName(), "中文零件")

    def test_ambiguous_candidates_rejected(self):
        # Real GB decoders usually agree for shared Chinese codepoints; exercise
        # the disagreement branch explicitly rather than making up a byte fixture.
        def fake(text, codec):
            if codec == "utf-8":
                raise ConversionError("bad escape")
            return codec, 1
        with patch("usd_scan.repair_escaped_strings", side_effect=fake):
            with self.assertRaises(ConversionError):
                choose_encoding(b"ascii")

    def test_utf8_and_gb_escaped_strings_preserve_values(self):
        source = self.root / "mixed.usda"
        source.write_text(
            '#usda 1.0\n'
            'def "Good" (displayName = "\\xe4\\xb8\\xad\\xe6\\x96\\x87") {}\n'
            'def "Bad" (displayName = "\\xd6\\xd0\\xce\\xc4") {}\n',
            encoding="utf-8")
        for encoding in ("auto-gb", "gb2312", "gbk", "gb18030"):
            with self.subTest(encoding=encoding):
                result = scan(self.root, fix=True, encoding=encoding,
                              output=self.base / encoding)
                stage = Usd.Stage.Open(str(Path(result["output"]) / source.name))
                self.assertTrue(result["complete"])
                self.assertEqual(stage.GetPrimAtPath("/Good").GetDisplayName(), "中文")
                self.assertEqual(stage.GetPrimAtPath("/Bad").GetDisplayName(), "中文")
                again = scan(Path(result["output"]), encoding=encoding)
                self.assertEqual(again["summary"], {"ok": 3})

    def test_explicit_gb_preserves_unicode_in_crate(self):
        layer = Sdf.Layer.CreateAnonymous()
        Sdf.PrimSpec(layer, "Good", Sdf.SpecifierDef).SetInfo("displayName", "正常🙂")
        Sdf.PrimSpec(layer, "Bad", Sdf.SpecifierDef).SetInfo("displayName", "中文".encode("gbk"))
        source = self.root / "mixed.usdc"
        layer.Export(str(source))
        for encoding in ("gb2312", "gbk", "gb18030"):
            with self.subTest(encoding=encoding):
                result = scan(self.root, fix=True, encoding=encoding,
                              output=self.base / encoding)
                stage = Usd.Stage.Open(str(Path(result["output"]) / source.name))
                self.assertTrue(result["complete"])
                self.assertEqual(stage.GetPrimAtPath("/Good").GetDisplayName(), "正常🙂")
                self.assertEqual(stage.GetPrimAtPath("/Bad").GetDisplayName(), "中文")

    def test_review_and_package_remain_unchanged(self):
        damaged = self.root / "damaged.usda"
        damaged.write_text('#usda 1.0\ndef "Bad" (displayName = "�") {}\n')
        package = self.root / "asset.usdz"
        package.write_bytes(b"PKfake")
        result = scan(self.root, fix=True)
        self.assertFalse(result["complete"])
        self.assertEqual(result["summary"]["review"], 1)
        self.assertEqual(result["summary"]["unsupported"], 1)
        for p in (damaged, package):
            self.assertEqual((Path(result["output"]) / p.name).read_bytes(), p.read_bytes())

    def test_overlay_preserves_paths_and_default_prim(self):
        labels = self.base / "labels.json"
        labels.write_text(json.dumps({"/World/Part_001": "底座", "/World/Part_002": "连接轴"}))
        result = scan(self.root, fix=True, entry=Path("scene.usda"), labels=labels)
        output = Path(result["output"])
        stage = Usd.Stage.Open(str(output / result["open_in_kit"]))
        self.assertEqual(str(stage.GetDefaultPrim().GetPath()), "/World")
        self.assertEqual(stage.GetPrimAtPath("/World/Part_001").GetDisplayName(), "底座")
        self.assertEqual(stage.GetPrimAtPath("/World/Part_002").GetDisplayName(), "连接轴")
        original = Usd.Stage.Open(str(output / "scene.usda"))
        self.assertEqual(original.GetPrimAtPath("/World/Part_001").GetDisplayName(), "机械臂底座")

    def test_overlay_unknown_prim_leaves_no_output(self):
        labels = self.base / "labels.json"
        labels.write_text('{"/Missing": "中文"}')
        with self.assertRaises(ConversionError):
            scan(self.root, fix=True, entry=Path("scene.usda"), labels=labels)
        self.assertFalse((self.base / "project.utf8").exists())

    def test_output_collision_or_nested_rejected(self):
        for output in (self.root, self.root / "fixed", self.base):
            with self.assertRaises(ConversionError):
                scan(self.root, fix=True, output=output)

    def test_symlink_not_followed_and_fix_rejected(self):
        (self.root / "linked").symlink_to(self.root, target_is_directory=True)
        result = scan(self.root)
        self.assertEqual(result["usd_files"], 2)
        self.assertEqual(result["symlinks"], ["linked"])
        self.assertFalse(result["complete"])
        with self.assertRaises(ConversionError):
            scan(self.root, fix=True)

    def test_idempotent_rescan(self):
        result = scan(self.root, fix=True)
        again = scan(Path(result["output"]))
        self.assertEqual(again["summary"], {"ok": 2})

    def test_utf8_mojibake_is_not_guessed(self):
        source = self.root / "unknown.usda"
        content = '#usda 1.0\ndef "Part" (displayName = "涓枃") {}\n'
        source.write_text(content)
        result = scan(self.root, fix=True)
        self.assertEqual((Path(result["output"]) / source.name).read_text(), content)


if __name__ == "__main__":
    unittest.main()
