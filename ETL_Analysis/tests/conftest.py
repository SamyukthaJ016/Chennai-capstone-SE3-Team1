import re
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


PLOTLY_BUNDLE_MARKER = "plotly.js v"
PLOTLY_CDN_HOST = "cdn.plot.ly"

_SCRIPT_SRC = re.compile(r'<script[^>]*\ssrc="([^"]+)"', re.IGNORECASE)


def _install_plotly_stub():
    try:
        import plotly.io
        return
    except ImportError:
        pass

    def to_html(figure, include_plotlyjs=True, full_html=True, config=None,
                default_width=None, **kwargs):
        js = ""
        if include_plotlyjs is True:
            js = (f'<script type="text/javascript">/**\n'
                  f'* {PLOTLY_BUNDLE_MARKER}0.0.0-stub\n*/</script>')
        elif include_plotlyjs == "cdn":
            js = (f'<script charset="utf-8" '
                  f'src="https://{PLOTLY_CDN_HOST}/plotly-2.32.0.min.js">'
                  f'</script>')
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


class HtmlDoc:

    def __init__(self, document: str):
        self.document = document

    def __len__(self):
        return len(self.document)

    def count(self, needle: str) -> int:
        return self.document.count(needle)

    def contains(self, needle: str) -> bool:
        return needle in self.document

    def assert_contains(self, *needles: str) -> None:
        missing = [n for n in needles if n not in self.document]
        assert not missing, f"missing from the report: {missing}"

    def assert_absent(self, *needles: str) -> None:
        present = [n for n in needles if n in self.document]
        assert not present, f"unexpectedly present in the report: {present}"

    def script_srcs(self) -> list[str]:
        return _SCRIPT_SRC.findall(self.document)

    def embedded_bundle_count(self) -> int:
        return self.document.count(PLOTLY_BUNDLE_MARKER)


@pytest.fixture
def html():
    return HtmlDoc
