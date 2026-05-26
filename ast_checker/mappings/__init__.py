from tree_sitter import Language

from .c import C_MAPPING
from .python import PYTHON_MAPPING

_MAPPINGS = {
    "Python3": PYTHON_MAPPING,
    "C": C_MAPPING,
}

_LANGUAGES: dict[str, Language] = {}


def _init_languages():
    try:
        import tree_sitter_python as tspython

        _LANGUAGES["Python3"] = Language(tspython.language())
    except ImportError:
        pass
    try:
        import tree_sitter_c as tsc

        _LANGUAGES["C"] = Language(tsc.language())
    except ImportError:
        pass


_init_languages()


def get_mapping(language: str) -> dict:
    return _MAPPINGS.get(language, {})


def get_language(language: str) -> Language | None:
    return _LANGUAGES.get(language)
