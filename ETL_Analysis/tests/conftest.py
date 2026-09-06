"""Make the repository root importable, stub plotly when it is absent, and
provide assertion helpers for the multi-megabyte report document.

Remove the sys.path block once the sprint's packaging metadata is in place and
the project is installed with `pip install -e`.
"""

import re
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# The banner comment plotly writes at the top of its embedded bundle. Present
# exactly once per embedded copy, and absent entirely in CDN mode, so counting
# it is how a test asks "how many copies of the library are in this file".
# The stub below emits the same banner, so an assertion means the same thing
# whether or not plotly is installed.
PLOTLY_BUNDLE_MARKER = "plotly.js v"
PLOTLY_CDN_HOST = "cdn.plot.ly"

_SCRIPT_SRC = re.compile(r'<script[^>]*\ssrc="([^"]+)"', re.IGNORECASE)


def _install_plotly_stub():
    """Stand in for plotly.io.to_html when plotly is not installed.

    The report's figure BUILDERS are pure and are what the tests mostly check.
    Only `_render` needs plotly, so a stub keeps the suite runnable on a
    machine without it -- while `test_report.py` still asserts how to_html is
    called: fragments not documents, and the bundle embedded exactly once.

    The stub imitates the SHAPE of plotly's own output -- the bundle banner,
    a `src=`-bearing script tag in CDN mode, one `plotly-graph-div` per figure
    -- so the assertions written against it hold against the real library too.
    A stub that invented its own markers would let the suite pass green on a
    machine without plotly and fail on a machine with it, which is what it
    used to do.

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
    """Assertions over a rendered report that stay cheap when they fail.

    An inline report is ~3.6MB, because the plotly bundle is embedded in it.
    A plain `assert "x" in document` that FAILS hands that whole string to
    pytest, which runs difflib over it to build the failure message. Measured
    on this suite: 3h57m to report six failures, almost all of it spent
    formatting them -- so a stale assertion presents as a hung suite rather
    than as a red test. Every helper here asserts on a short derived value
    instead, so a failure is a normal, readable failure.
    """

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
        """Every URL the document would fetch a script from.

        Empty means the page renders with no network, which is the sprint's
        artefact rule. Asserting on this list rather than on the absence of a
        hostname is what makes the check honest: plotly's own bundle mentions
        its CDN in a comment, so a substring search for `cdn.plot.ly` reports
        a network dependency that is not there.
        """
        return _SCRIPT_SRC.findall(self.document)

    def embedded_bundle_count(self) -> int:
        """Copies of the plotly library embedded in the document."""
        return self.document.count(PLOTLY_BUNDLE_MARKER)


@pytest.fixture
def html():
    """Wrap a rendered document in `HtmlDoc`. See that class for why."""
    return HtmlDoc
