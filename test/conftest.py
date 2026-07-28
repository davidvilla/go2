# Loads the repository's go2.py by explicit file path, bypassing sys.path
# search entirely. Two problems this avoids:
#
# - There is a stale `go2.py` installed at
#   /usr/lib/python3/dist-packages/go2.py (an old package copy); a plain
#   `import go2` from the tests would silently resolve to that one instead
#   of this repository's version.
#
# - The repo root also contains a dead `code.py` (2011 scratch file) that
#   shadows the stdlib `code` module. If the repo root is ever put in front
#   of the stdlib on sys.path (e.g. `PYTHONPATH=.`, or `python -m pytest`
#   run from the repo root, which inserts cwd at sys.path[0]), pytest's own
#   `import pdb` -> `import code` picks up that file instead and crashes.
#   Loading go2.py by path sidesteps sys.path entirely for module
#   resolution, so this file must NOT be made importable via sys.path
#   tricks. Run the suite with the `pytest` console script (not
#   `python -m pytest`) from the repo root, or from anywhere else.

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_by_path(name, fname):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_REPO_ROOT, fname))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if 'go2' not in sys.modules:
    # go2.py does `from osfs import ...`; pre-registering osfs here means
    # that import is satisfied straight from sys.modules, with no sys.path
    # search involved (go2.py's own sys.path bootstrap can't help here when
    # the repo root also happens to be the cwd, as it is under pytest: its
    # `sys.path.append(dirname(__file__))` followed by
    # `sys.path.remove(os.getcwd())` cancels itself out in that case).
    _load_by_path('osfs', 'osfs.py')
    _load_by_path('go2', 'go2.py')

import go2  # noqa: E402  (must come after the sys.modules pre-registration above)


@pytest.fixture(autouse=True)
def isolate_go2_config_file(tmp_path, monkeypatch):
    "Never let a test read/write the real user's ~/.go2/config"
    monkeypatch.setattr(go2, 'GO2CONFIG', str(tmp_path / 'go2-config-unused'))
