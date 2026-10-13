# USD 中文编码修复工具

**先读 [安装与运行环境检查](INSTALL.md)**：Python/SDK 前置要求、缺失依赖安装方法、Windows/macOS/Linux 步骤和离线安装。

正式 CLI 名称为 **`usd-utf8`**，版本 **0.2.0**。安装后执行 `usd-utf8 doctor` 检查环境，`usd-utf8 scan "/工程目录" --fix` 扫描并修复。`--help` 查看用法，子命令后的 `--json` 输出 JSON。下文的 `python usd_utf8.py ...` 仍可用于源码运行，输出保持 JSON。

用于扫描第三方软件导出的 USD 工程，检测并修复 GB2312／GBK／GB18030 编码问题。包含目录扫描、工程副本修复、中文显示名覆盖层、单文件转换、Omniverse Kit 环境探针和测试。工具更新：2026-10-11；版本资料核实：2026-10-10。

## 推荐：扫描整个工程并修复

在工具目录执行（本机 `.venv` 已安装 SDK）：

```bash
# 只扫描，不修改或复制文件
.venv/bin/python usd_utf8.py scan "/path/to/project"

# 扫描后自动修复，输出到相邻的 project.utf8 目录
.venv/bin/python usd_utf8.py scan "/path/to/project" --fix

# 指定输出目录；不会覆盖已有目录
.venv/bin/python usd_utf8.py scan "/path/to/project" --fix -o "/path/to/project_fixed"
```

Windows 使用 `.venv\Scripts\python.exe` 替代 `.venv/bin/python`。

扫描递归检查 `.usd/.usda/.usdc/.usdz`，用文件头确认内容格式，用 SDK 进行单层解析。结果分为：

| 状态 | 含义与操作 |
| --- | --- |
| `ok` | 编码与单层解析检查通过，原样保留；不能据此排除二次乱码或字体问题 |
| `repairable` | 能严格恢复，等待修复；`--fix` 后变成 `fixed` |
| `review` | 编码候选不一致、文件损坏、已有 `�` 等，原样保留并列出原因 |
| `unsupported` | 例如 USDZ 包，原样保留，需专门处理 |

`--fix` 会复制工程中的资源，保留文件名、子目录及内部相对引用，然后只替换副本中可修复的 USD。**原工程不修改**。所以需要容纳一份完整工程的磁盘空间；`.git/.venv/__pycache__` 不复制、不扫描。存在符号链接时不跟随扫描，也不生成修复副本。

副本根目录写入 `_usd_utf8_scan.json`，记录文件状态、预览、中文显示名、引用和校验值。`complete=false` 或退出码 1 表示仍有需要处理的文件；问题文件原样保留不代表它们已修好。退出码 2 表示参数、环境或写入失败。默认不会创建缺失的输出父目录。

默认 `auto-gb` 的前提是来源属于 UTF-8／GB 系列：先尝试 UTF-8，失败后尝试 GB 系列，只有所有成功候选产生完全相同的文字才自动修复。它不是通用编码识别器；如果来源可能是日文 Shift-JIS、Big5 等，不能直接使用这个假设。也可以指定 `--encoding gbk`，但已通过检查的 UTF-8 文件仍优先保留。

USDC 导出中“正常 UTF-8 中文＋GB 转义字符串”可分别处理，正常文字保持不变。任意混合原始编码、同一个字符串中混用多种字节编码，仍不能保证可靠自动识别。

**中文显示名覆盖层（可选）**：如果需要为英文 Prim 路径补充中文名称，准备映射文件 `labels.json`：

```json
{
  "/World/Part_001": "机械臂底座",
  "/World/Part_002": "连接轴"
}
```

```bash
.venv/bin/python usd_utf8.py scan "/path/to/project" --fix \
  --entry scene.usd --labels "/path/to/labels.json"
```

在修复副本中生成同目录 `scene.chinese.usda`，以 `scene.usd` 为 sublayer，通过 `over` 补充 `displayName`。打开报告 `open_in_kit` 指向的文件，在 Stage 开启 Show Display Names 并启用中文字体。Prim、关节、关系目标路径均不改名。映射目标必须能在未加载 payload 的 Stage 中找到，且不能是实例代理；不满足时不发布副本。

没有原始中文名称的数据不能凭空恢复，工具不会自动推断 `Part_001` 应叫什么。已有显示名会检查并保留；字体和 Stage 设置由 Kit 端诊断，不是文件编码修复操作。

绝对资源路径、工程目录外引用、自定义 resolver 不会被自动重定向；建议扫描一个包含所有相对依赖的工程目录。检查范围是逐层解析，普通 `--fix` 不代表整个仿真场景已经完成组合或运行验证。

## 先明确：什么版本支持中文？

| 层面 | 结论 | 使用条件 |
| --- | --- | --- |
| OpenUSD 的真实 Prim 名称，例如 `/装配/螺栓` | **24.03 起支持 UTF-8 标识符** | 仍需满足 Unicode 标识符规则；空格、路径分隔符等不能任意出现在名称里 |
| string、token、asset 值及 `displayName` | UTF-8 支持早于 24.03 | 不应把 24.03 误认为 USD 首次支持中文字符串的版本 |
| Omniverse Stage 显示名称 | 支持 `displayName`，可开启 **Show Display Names** | 显示名称和真实 Prim 路径是两个字段 |
| `omni.ui` 中文字形 | 可以显示中文，但需要中文字体支持 | Kit 109.0 发布说明明确列出 `omni.kit.language.simplified_chinese` 1.0.3；这不等于它是所有 UI 中文能力的最早版本 |

“ov-ui library”在本项目中暂按 **Omniverse Kit 的 `omni.ui`** 理解。如果指其他库，需要另外核查。

依据：

- [OpenUSD 官方 Unicode 文档](https://openusd.org/release/api/_usd__page__u_t_f_8.html)：24.03 扩展路径和元数据标识符支持；验证 Prim 名称使用 `Sdf.Path.IsValidIdentifier`，不要使用仍可能仅接受 ASCII 的 `Tf` 名称清理函数。
- [OpenUSD 2024 SIGGRAPH 发布材料](https://openusd.org/files/BOFSiggraph2024.pdf)：UTF-8 identifiers released in 24.03。
- [Omniverse Stage Options](https://docs.omniverse.nvidia.com/extensions/latest/ext_core/ext_stage/options.html)：Show Display Names 的功能及对应设置。
- [Kit 109.0 发布说明](https://docs.omniverse.nvidia.com/dev-guide/latest/release-notes/109_0.html)：简体中文字体扩展支持。
- [Unity Connector 导出说明](https://docs.omniverse.nvidia.com/connect/latest/unity/manual/export.html)：部分连接器仍把名称转成 ASCII，并将原名保存在 `displayName`；此连接器限制不能当成现代 OpenUSD 的通用限制。

OpenUSD 版本达标，不代表特定设计软件、连接器或 UI 编辑控件都已更新其名称验证。应在目标应用内部执行探针，而不是仅检查独立 Python 安装的版本。

## 快速使用

需要 64 位 Python 3.10–3.14；推荐具有对应 `usd-core` wheel 的 Python 3.12。本机开发目录有专用 `.venv`，安装了 OpenUSD 26.8；下载的 ZIP 不包含虚拟环境，需要按照 INSTALL.md 安装。

macOS／Linux 新环境安装：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Windows 新环境安装：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

以下在本工具目录执行；Windows 将 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。

```bash
# 1. 检查当前 Python 的 OpenUSD 支持
.venv/bin/python usd_utf8.py doctor

# 2. 检查实际格式，查看各候选编码下的中文预览
.venv/bin/python usd_utf8.py inspect /path/to/model.usd

# 3. 预览 GBK 转换并进行 USD 单层解析验证，不写文件
.venv/bin/python usd_utf8.py convert /path/to/model.usd --encoding gbk --dry-run

# 4. 正式输出到同目录 model.utf8.usd，保留原文件
.venv/bin/python usd_utf8.py convert /path/to/model.usd --encoding gbk
```

如果来源明确是 GB2312 或 GB18030，使用相应 `--encoding gb2312` 或 `--encoding gb18030`。GB18030 可覆盖更广字符集，但“解码不报错”不代表选对了编码；请对照原设计名称判断预览。

指定同目录输出名或改变容器格式：

```bash
.venv/bin/python usd_utf8.py convert /path/to/model.usda --encoding gbk -o /path/to/model.fixed.usdc
.venv/bin/python usd_utf8.py convert /path/to/model.usdc --encoding gbk -o /path/to/model.fixed.usda
```

没有 SDK 时，可以检测文本文件，或显式跳过文本的 USD 解析验证：

```bash
python3 usd_utf8.py inspect /path/to/model.usda
python3 usd_utf8.py convert /path/to/model.usda --encoding gbk --skip-usd-validation
```

这时仅确认编码可转换，**不代表输出 USD 语法有效**。USDC 输入或输出必须使用 SDK。

## 转换行为

- 按文件头识别 `#usda 1.0` 和 `PXR-USDC`，不根据 `.usd` 后缀猜测容器。
- 文本先按所选源编码解码，再编码成无 BOM 的 UTF-8；不先把 GB 文件交给 USD 解析器。
- `auto` 只接受 UTF-8，不自动猜测 GB 编码。检测同时报告文本字节和字符串转义内容的 UTF-8 有效性。
- SDK 有时把 USDC 非法字符串字节导出成 `\xd6\xd0...`。工具识别引号内的十六进制／八进制字节转义，按所选编码恢复中文。字面量 `\\xd6` 和注释不会被当成字节转义。
- USDC 使用 `Sdf.Layer` 导出、修复和重新封装，不直接修改 crate 二进制。SDK 不能读取或导出的损坏容器会报错。
- 默认验证单个 layer 的 USD 语法；USDC 输出还进行重新读取和序列化一致性校验。不 flatten、不打开整个 composed stage、不自动加载依赖。
- 保留数值、几何数据和 USD 结构。纯文本常规转码保留换行与排版；转义修复或 USDC 导出可能改变文字表示与排版。
- 不覆盖源文件或任何已有输出，包括符号链接。输出先写临时文件，再以硬链接原子发布；目标文件系统须支持硬链接（常规 APFS、NTFS、ext4 支持）。不支持时会报错，可在支持的本地磁盘处理后复制回去。
- 输出报告包含预览、源和输出 SHA-256、SDK 版本、外部资源引用以及验证范围。

## 哪些情况不适合直接转码？

| 现象 | 原因与处理 |
| --- | --- |
| `□□□`，但 `GetName()`／`GetDisplayName()` 输出正确 | 字体缺字。安装或启用对应 Kit 中文字体扩展 |
| `displayName` 中文正确，Stage 显示 `Part_001` | 开启 Show Display Names |
| 文件已经是 UTF-8，但中文变成“涓…”等乱码 | 可能已发生二次误解码。需要明确历史编码链，本工具不自动猜测逆变换 |
| 中文名称变成下划线、`GameObject_1` | 查看 `displayName` 或原名元数据；若已丢弃原字符，只能从原始设计文件恢复 |
| 字符已变成 `�` 或 `?` | 原字节可能已不可恢复。发现 `�` 默认阻止转换；`--allow-replacement` 只允许保留，不会恢复。工具不能区分有意输入的 `?` 与丢失字符 |
| 同一层混合 UTF-8 和 GB 编码 | 全层使用单一源编码不适用；严格解码也无法可靠识别所有混合情况。需要真实样本和字段级规则，不能以“验证通过”推断中文正确 |
| 非法字节位于 USDC 的 Prim 路径，SDK 无法读取 | 需原导出器重新导出或专门修复。不能保证任意损坏的 crate 都可恢复 |
| USDZ | 不直接处理；须用 USD 工具解包、修复并正确重新打包 |

`convert` 命令仅处理指定的单层文件。引用层、payload、纹理和磁盘文件名不会自动转换或改名；其他文件中引用原 Prim 名称的路径也不会被同步修改。默认同目录输出是为了保留相对资源的解析基准；`--allow-relocation` 允许跨目录保存，但维护相对路径由调用者负责。多层工程建议使用上面的 `scan --fix` 模式，之后验证最终组合结果。

## 在 Omniverse 中诊断

把 `kit_probe.py` 的内容粘贴到目标应用的 Script Editor 执行：

1. 输出实际 `Usd.GetVersion()` 和中文名称验证结果。
2. 在匿名内存 Stage 创建 `/中文零件`，不修改当前场景。
3. 列出 `omni.ui`、Stage 组件及中文字体扩展的启用信息。
4. 弹出中英文 Label 测试窗口，人工确认中文是否显示为方框。

Stage 右上角 Options → **Show Display Names** 可显示已有的中文 `displayName`。

针对已提供该扩展的 Kit 应用，可以在 Extension Manager 中启用 `omni.kit.language.simplified_chinese`，按照具体应用提示重启。只安装独立 `usd-core` 不会为 Kit 安装字体。

`kit_probe.py` 是诊断脚本；本机没有运行 Kit，所以未实测目标软件的 UI 字形或编辑行为。

## 示例与验证

`examples/assembly.gbk.usda`：GBK 编码的中文 Prim、元数据、属性、关系路径样例。

`examples/assembly.utf8.usda`：对应 UTF-8 文本，OpenUSD 24.03+ 可读取中文 Prim。

`examples/displayname.gbk.usdc`：真实 USDC，`displayName` 内故意存入非法 GBK 字节，用于验证 SDK 导出转义后的修复流程。

```bash
.venv/bin/python usd_utf8.py inspect examples/assembly.gbk.usda
.venv/bin/python usd_utf8.py convert examples/assembly.gbk.usda --encoding gbk --dry-run
.venv/bin/python usd_utf8.py convert examples/displayname.gbk.usdc --encoding gbk --dry-run
.venv/bin/python -m unittest -v
```

开发验证环境：macOS、Python 3.12.12、usd-core 26.8。40 项测试通过，覆盖三种 GB 编码、GB18030 四字节字符、GBK 尾字节反斜杠、转义字节、UTF-8 幂等、覆盖保护、错误输入拒绝、引用保持、中文 Prim 和关系路径、真实 GBK 元数据 USDC 的修复与二进制往返。目录扫描测试覆盖工程副本内子层和纹理解析、正常 Unicode 与 GB 转义共存、二次扫描幂等、疑难文件保留、符号链接保护、显示名覆盖层及默认 Prim 保留。CLI 测试覆盖帮助、版本、缺少 SDK、不支持的 Python、安装提示及环境检查；另外验证 wheel 安装后从其他目录调用，以及找不到 Python 时的 shell 启动器提示。

尚未用用户的第三方软件实际导出文件验收；Windows/Linux 和目标 Omniverse 应用尚未实机验证。解析成功验证的是 USD 结构，并不能证明所选编码的语义一定正确。
