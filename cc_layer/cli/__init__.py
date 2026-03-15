"""
CLI tools for MiroFish CC Layer.

All CLIs follow the same contract:
- Input: argparse arguments (JSON strings or file paths)
- Output: stdout JSON (success) or stderr log + exit code 1 (failure)
- Import existing backend services directly (no logic duplication)
"""
import sys
import os
import types

# Add backend to Python path so we can import app.services.*
_backend_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
if os.path.isdir(_backend_dir):
    _backend_dir = os.path.abspath(_backend_dir)
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)

# Prevent app/__init__.py and sub-package __init__.py from running
# (they import Flask, OpenAI, etc.). Register them as namespace packages
# so individual modules (app.models.life_simulator, etc.) can be imported.
_app_dir = os.path.join(_backend_dir, 'app')
for pkg_name, pkg_subdir in [
    ('app', ''),
    ('app.models', 'models'),
    ('app.services', 'services'),
    ('app.utils', 'utils'),
]:
    if pkg_name not in sys.modules:
        mod = types.ModuleType(pkg_name)
        mod.__path__ = [os.path.join(_app_dir, pkg_subdir) if pkg_subdir else _app_dir]
        mod.__package__ = pkg_name
        sys.modules[pkg_name] = mod

# Provide a stub for 'openai' if not installed, so modules that import
# `from openai import OpenAI` at module level don't crash.  The stub's
# OpenAI class will raise on instantiation, but module-level import succeeds.
if 'openai' not in sys.modules:
    try:
        import openai as _openai  # noqa: F401 — real package available
    except ImportError:
        _openai_stub = types.ModuleType('openai')

        class _OpenAIStub:
            def __init__(self, *a, **kw):
                raise ImportError(
                    "openai package is not installed. "
                    "Install it with: pip install openai"
                )

        _openai_stub.OpenAI = _OpenAIStub
        sys.modules['openai'] = _openai_stub

# Provide a stub for 'tavily' if not installed.
if 'tavily' not in sys.modules:
    try:
        import tavily as _tavily  # noqa: F401
    except ImportError:
        _tavily_stub = types.ModuleType('tavily')

        class _TavilyClientStub:
            def __init__(self, *a, **kw):
                raise ImportError(
                    "tavily-python package is not installed. "
                    "Install it with: pip install tavily-python"
                )

        _tavily_stub.TavilyClient = _TavilyClientStub
        sys.modules['tavily'] = _tavily_stub
