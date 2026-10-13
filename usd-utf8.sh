#!/bin/sh
# Source-checkout launcher. Never downloads or installs packages automatically.
tool_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 2
if [ -x "$tool_dir/.venv/bin/python" ]; then
    exec "$tool_dir/.venv/bin/python" "$tool_dir/usd_cli.py" "$@"
fi
for python_cmd in python3.12 python3.13 python3.11 python3.10 python3.14 python3 python; do
    if command -v "$python_cmd" >/dev/null 2>&1; then
        exec "$python_cmd" "$tool_dir/usd_cli.py" "$@"
    fi
done
echo "Python not found. Install 64-bit Python 3.12: https://www.python.org/downloads/" >&2
echo "Then run: python3.12 -m venv .venv" >&2
echo "          .venv/bin/python -m pip install ." >&2
echo "See INSTALL.md in the extracted tool directory." >&2
exit 2
