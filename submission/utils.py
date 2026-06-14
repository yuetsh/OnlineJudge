import subprocess

CLANG_FORMAT_STYLE = "{BasedOnStyle: LLVM, IndentWidth: 4, BreakBeforeBraces: Attach}"


class FormatSyntaxError(Exception):
    """格式化工具因代码本身存在语法错误而失败（目前只有 ruff format 会触发）"""


class FormatToolError(Exception):
    """格式化工具执行本身失败：超时、二进制缺失、非预期的非零退出码"""


def format_code(code, language):
    """
    :param code: 用户代码
    :param language: "python" | "c" | "cpp"
    :return: 格式化后的代码字符串
    :raises FormatSyntaxError: 代码语法错误导致格式化失败（仅 python）
    :raises FormatToolError: 格式化工具本身执行失败
    """
    if language == "python":
        return _format_with_ruff(code)
    return _format_with_clang(code, language)


def _format_with_ruff(code):
    try:
        result = subprocess.run(
            ["ruff", "format", "--stdin-filename", "code.py", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise FormatToolError(str(e))
    if result.returncode != 0:
        raise FormatSyntaxError(result.stderr)
    return result.stdout


def _format_with_clang(code, language):
    filename = "code.c" if language == "c" else "code.cpp"
    try:
        result = subprocess.run(
            [
                "clang-format",
                f"-assume-filename={filename}",
                f"-style={CLANG_FORMAT_STYLE}",
            ],
            input=code,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        raise FormatToolError(str(e))
    if result.returncode != 0:
        raise FormatToolError(result.stderr)
    return result.stdout
