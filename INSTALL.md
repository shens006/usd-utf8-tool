# 安装与运行环境检查

## 1. 先检查什么？

| 项目 | 要求 | 缺少时怎么办 |
| --- | --- | --- |
| Python | 64 位 CPython 3.10–3.14，推荐 3.12 | 从 [Python 官网](https://www.python.org/downloads/) 安装对应版本；不要直接选不在此范围的最新版 |
| pip | 用于安装依赖 | `python -m ensurepip --upgrade`；发行版 Python 可使用系统的 pip 包 |
| venv | 建议使用独立虚拟环境 | Linux 安装发行版对应的 `python3-venv` 或 `python3.12-venv` 包 |
| OpenUSD | `usd-core>=24.3` | 安装本工具时自动安装；已安装环境缺少时按 doctor 给出的命令补装 |
| 平台 | 与 usd-core wheel 对应的 OS / Python / CPU 架构 | 没有匹配 wheel 时使用支持的 64 位 Python/机器，或自行准备兼容的 OpenUSD Python SDK |
| 磁盘 | `scan --fix` 需要一份完整工程副本的空间和输出写入权限 | 扫描报告列出工程体积；选择有足够空间的输出目录 |
| GPU / Isaac Sim / Kit | **离线扫描、修复不需要安装** | 字体和 Stage 显示需在目标 Isaac Sim / Kit 内另行检查 |

SDK 的具体平台支持以 [usd-core 发布文件](https://pypi.org/project/usd-core/#files) 为准。工具当前在 macOS + Python 3.12 + OpenUSD 26.8 上实测；Windows/Linux 提供安装步骤与启动器，尚未实机验收。

## 2. 不安装 CLI 也能先检查

解压源代码包，进入 `usd-utf8-tool` 目录。

macOS / Linux：

```bash
sh ./usd-utf8.sh doctor
```

Windows PowerShell：

```powershell
.\usd-utf8.cmd doctor
```

启动器优先使用工具目录的 `.venv`。没有 Python 时给出下载地址；Python 存在但版本或 SDK 不满足要求时输出具体原因和安装步骤。检查不安装、不下载任何软件。

`doctor` 只检查运行环境与中文 Prim 解析，不扫描工程磁盘空间，也不能验证 Isaac Sim 字体是否正常。扫描命令也会检查 SDK 是否可加载、版本是否足够。

## 3. 安装正式 CLI

以下命令必须在解压后的工具目录（包含 `pyproject.toml`）执行。安装只进入独立 `.venv`，不要对 Isaac Sim 内置 Python 执行升级 usd-core 的命令。

### macOS / Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .

# 激活后即可使用短命令
source .venv/bin/activate
usd-utf8 --version
usd-utf8 doctor
```

若不希望激活，每次使用 `.venv/bin/usd-utf8`，或继续使用 `sh ./usd-utf8.sh`。

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install .

# 不需要修改 PowerShell 执行策略，也不需要激活
.venv\Scripts\usd-utf8.exe --version
.venv\Scripts\usd-utf8.exe doctor
```

如果已激活该虚拟环境，也可直接使用 `usd-utf8`。安装过程中需要网络，或者事先准备好离线 wheel 文件。

### 使用 wheel 安装包

工具的 `dist/` 内提供 `usd_utf8_tool-0.2.0-py3-none-any.whl`。在已准备好的虚拟环境中执行：

```bash
python -m pip install dist/usd_utf8_tool-0.2.0-py3-none-any.whl
usd-utf8 doctor
```

wheel 只包含 CLI 代码；OpenUSD 是平台相关依赖，pip 会另行获取。如果需要完全离线安装，在同平台、同 Python 版本的联网机器准备依赖：

```bash
python -m pip download --only-binary=:all: -d wheels dist/usd_utf8_tool-0.2.0-py3-none-any.whl
```

将 `wheels` 目录复制到目标机器，在目标虚拟环境执行：

```bash
python -m pip install --no-index --find-links wheels usd-utf8-tool==0.2.0
```

## 4. 日常使用

```bash
# 环境检查
usd-utf8 doctor

# 扫描，终端显示各文件状态，不修改工程
usd-utf8 scan "/path/to/project"

# 自动修复到相邻 project.utf8 目录
usd-utf8 scan "/path/to/project" --fix

# 指定副本目录；父目录须存在
usd-utf8 scan "/path/to/project" --fix -o "/path/to/project_fixed"

# 明确知道源编码时指定 GBK
usd-utf8 scan "/path/to/project" --fix --encoding gbk

# 输出 JSON，方便脚本集成
usd-utf8 scan "/path/to/project" --json

# 单文件检查及转换预览
usd-utf8 inspect "/path/to/model.usd"
usd-utf8 convert "/path/to/model.usd" --encoding gbk --dry-run

# 查看所有选项
usd-utf8 --help
usd-utf8 scan --help
```

Windows 将示例路径替换为 `"D:\assets\project"` 等实际路径；没有激活环境时，用 `.venv\Scripts\usd-utf8.exe` 代替命令名。

命令退出码：0 = 命令成功；1 = doctor 未就绪，或 scan 存在人工处理项；2 = 参数、环境依赖、读写或转换错误。扫描发现可自动修复项但尚未执行 `--fix` 时可以返回 0，请结合 `summary` 判断是否需要修复。

正常文件原样保留，可修复文件写入工程副本；未解决项保留原样并列入 `_usd_utf8_scan.json`。字体缺失、已经丢失的原名、不能确定的二次乱码不会被自动修复。详细规则及中文显示名覆盖层示例见 [README.md](README.md)。

## 5. 常见安装错误

| 报错 | 处理 |
| --- | --- |
| `python3.12` / `py` 找不到 | 安装 Python；Windows 安装后重开终端。也可用已安装的受支持版本替换命令 |
| `No module named venv` / `ensurepip is not available` | Linux 安装发行版的 venv/ensurepip 支持，再创建环境 |
| `No module named pip` | `.venv` 的 Python 执行 `-m ensurepip --upgrade` |
| `No module named pxr` | 在当前虚拟环境执行 `python -m pip install "usd-core>=24.3"`；doctor 会显示实际解释器路径 |
| `No matching distribution found` | 升级 pip 并核对 Python、OS、CPU 架构及 [wheel 列表](https://pypi.org/project/usd-core/#files)；不是所有 ARM/Linux 组合都有官方 wheel |
| `DLL load failed` / `dlopen` | 确认 SDK 与解释器架构一致；在全新独立环境重装，避免混用 Kit 与 pip 的 pxr 库 |
| `externally-managed-environment` | 使用本文的 `.venv`，不要修改系统 Python |
| 代理、证书或网络超时 | 核对网络、组织代理及 pip 源；可改用离线 wheel 安装 |
| `usd-utf8` 找不到 | 激活环境，或使用 `.venv/bin/usd-utf8` / `.venv\Scripts\usd-utf8.exe` |
| 输出目录已经存在 | 选择新的目录名；工具不会覆盖已有工程 |

参考：[Python venv 官方说明](https://docs.python.org/3/library/venv.html)、[Python 下载](https://www.python.org/downloads/)、[usd-core 官方 PyPI 包](https://pypi.org/project/usd-core/)。
