"""Repository shim to expose src package during local runs/tests.

This inserts the `src` directory into the package __path__ so
`python -m flights.__main__` and tests can import the package
without installing it.
"""

import importlib
import os

_this_dir = os.path.dirname(__file__)
_src_pkg = os.path.join(_this_dir, "src", "flights")
# Prefer inserting the package subdirectory so package submodules like
# `flights.__main__` resolve correctly when using `-m`.
if os.path.isdir(_src_pkg):
    __path__.insert(0, _src_pkg)
else:
    # Fallback: if package subdir not present, fall back to src (best-effort)
    _src = os.path.join(_this_dir, "src")
    if os.path.isdir(_src):
        __path__.insert(0, _src)

# Try to import the real package from the inserted path and re-export metadata
try:
    real = importlib.import_module("flights")
    if hasattr(real, "__version__"):
        __version__ = real.__version__
    if hasattr(real, "__all__") and isinstance(real.__all__, list):
        __all__ = list(real.__all__)  # type: ignore[assignment]
except Exception:
    # Best-effort: leave only __path__ configured; tests will import submodules
    pass

# If importing the package above recursed into this shim (and didn't set
# __version__), load the package's source __init__.py directly into a
# temporary module and read __version__ from it. This avoids recursive
# import of the same package name.
try:
    if "__version__" not in globals():
        impl_init = os.path.join(_this_dir, "src", "flights", "__init__.py")
        if os.path.isfile(impl_init):
            import importlib.util

            spec = importlib.util.spec_from_file_location("_flights_impl", impl_init)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
            else:
                mod = None
            if mod is not None and hasattr(mod, "__version__"):
                __version__ = mod.__version__  # type: ignore[attr-defined]
except Exception:
    # Ignore; leaving __version__ unset will surface errors in tests which
    # explicitly require it.
    pass