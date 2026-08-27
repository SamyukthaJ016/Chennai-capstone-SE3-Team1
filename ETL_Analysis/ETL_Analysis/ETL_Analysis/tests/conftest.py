"""Make the repository root importable, and stub plotly when it is absent.

Remove the sys.path block once the sprint's packaging metadata is in place and
the project is installed with `pip install -e`.
"""

import json
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_plotly_stub():
    """Stand in for plotly.io.to_html when plotly is not installed.

    The report's figure BUILDERS are pure and are what the tests mostly check.
    Only `_render` needs plotly, so a stub keeps the suite runnable on a
    machine without it -- while `test_report.py` still asserts how to_html is
    called: fragments not documents, and the 3MB bundle embedded exactly once.

    If plotly IS installed, this does nothing and the real library is used.
    """
    try:
        import plotly.io  # noqa: F401
        return
    except ImportError:
        pass

    def to_html(figure, include_plotlyjs=True, full_html=True, config=None,
                default_width=None, **kwargs):
        js = ""
        if include_plotlyjs is True:
            js = "<script>/*plotly-bundle*/</script>"
        elif include_plotlyjs == "cdn":
            js = '<script src="https://cdn.plot.ly/plotly-2.min.js"></script>'
        title = figure.get("layout", {}).get("title", {}).get("text", "")
        return (f'{js}<div class="plotly-graph-div" '
                f'data-traces="{len(figure.get("data", []))}">{title}</div>')

    io_module = types.ModuleType("plotly.io")
    io_module.to_html = to_html
    package = types.ModuleType("plotly")
    package.io = io_module
    sys.modules.setdefault("plotly", package)
    sys.modules.setdefault("plotly.io", io_module)


_install_plotly_stub()
