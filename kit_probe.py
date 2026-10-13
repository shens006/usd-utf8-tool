"""Paste into Kit Script Editor. Tests an anonymous stage; does not edit the open scene."""
import json
from pxr import Sdf, Usd

result = {"usd_version": Usd.GetVersion(),
          "chinese_identifier": Sdf.Path.IsValidIdentifier("中文零件")}
try:
    stage = Usd.Stage.CreateInMemory()
    prim = stage.DefinePrim("/中文零件", "Xform")
    prim.SetDisplayName("中文显示名称")
    result["prim_name"] = prim.GetName()
    result["display_name"] = prim.GetDisplayName()
except Exception as exc:
    result["prim_error"] = str(exc)

try:
    import carb.settings
    import omni.kit.app
    import omni.ui as ui
    manager = omni.kit.app.get_app().get_extension_manager()
    result["extensions"] = {}
    for name in ("omni.ui", "omni.kit.widget.stage", "omni.kit.window.stage",
                 "omni.kit.language.simplified_chinese"):
        ext_id = manager.get_enabled_extension_id(name)
        result["extensions"][name] = ext_id or "not enabled"
    result["show_display_names"] = carb.settings.get_settings().get(
        "/persistent/ext/omni.kit.widget.stage/show_prim_displayname")
    # Keep a global reference so the window remains alive in Script Editor.
    usd_utf8_probe_window = ui.Window("USD UTF-8 Font Probe", width=480, height=140)
    with usd_utf8_probe_window.frame:
        with ui.VStack():
            ui.Label("ASCII: Part_001")
            ui.Label("中文测试：装配 零件 螺栓")
            ui.Label("If Chinese appears as boxes, check CJK fonts.")
    result["font_test"] = "请目视检查测试窗口；创建 Label 成功不代表字形能显示。"
except ImportError:
    result["kit"] = "not running inside Omniverse Kit"
except Exception as exc:
    result["kit_error"] = str(exc)

print(json.dumps(result, ensure_ascii=False, indent=2))
