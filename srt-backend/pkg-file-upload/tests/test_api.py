import importlib

from pkg_file_upload.api import __all__ as public_names


def test_public_api_all_names_are_resolvable() -> None:
    mod = importlib.import_module("pkg_file_upload.api")
    for name in public_names:
        assert hasattr(mod, name), f"{name} in __all__ but not defined in api"
