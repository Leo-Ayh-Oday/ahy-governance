"""Plugin scaffold generator — ``python -m ahy_governance scaffold --type=detector --name=MyDetector``.

Generates::

    plugins/my_detector/
    ├── __init__.py
    ├── detector.py          ← implement ConflictDetector.detect()
    └── test_detector.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from textwrap import dedent


TEMPLATES: dict[str, dict[str, str]] = {
    "detector": {
        "module": "detector.py",
        "body": dedent("""\
        from ahy_governance.interfaces import ConflictDetector, ConflictResult


        class {ClassName}(ConflictDetector):
            \"\"\"{doc_title}\"\"\"

            def name(self) -> str:
                return "{slug}"

            def detect(self, agents: list, context: dict) -> list[ConflictResult]:
                results = []
                # TODO: implement your detection logic here
                return results
        """),
    },
    "channel": {
        "module": "channel.py",
        "body": dedent("""\
        from ahy_governance.interfaces import NotifyChannel


        class {ClassName}(NotifyChannel):
            \"\"\"{doc_title}\"\"\"

            def name(self) -> str:
                return "{slug}"

            async def send(self, message: dict) -> bool:
                # TODO: implement your notification delivery
                return True

            def health_check(self) -> bool:
                # TODO: verify the channel is reachable
                return True
        """),
    },
    "tracker": {
        "module": "tracker.py",
        "body": dedent("""\
        from ahy_governance.interfaces import CostTracker


        class {ClassName}(CostTracker):
            \"\"\"{doc_title}\"\"\"

            def name(self) -> str:
                return "{slug}"

            def estimate(self, request: dict) -> float:
                # TODO: implement cost estimation per model/provider
                return 0.0

            def should_throttle(self, agent_id: str, budget_limit: float) -> bool:
                # TODO: implement throttling logic
                return False
        """),
    },
}

INIT_TEMPLATE = dedent("""\
from .{module_base} import {ClassName}

__all__ = ["{ClassName}"]
""")

TEST_TEMPLATES: dict[str, str] = {
    "detector": dedent("""\
import pytest
from plugins.{slug}.detector import {ClassName}


def test_name():
    d = {ClassName}()
    assert d.name() == "{slug}"


def test_detect_empty():
    d = {ClassName}()
    results = d.detect([], {})
    assert isinstance(results, list)
"""),
    "channel": dedent("""\
import pytest
from plugins.{slug}.channel import {ClassName}


def test_name():
    c = {ClassName}()
    assert c.name() == "{slug}"


def test_health_check():
    c = {ClassName}()
    assert isinstance(c.health_check(), bool)
"""),
    "tracker": dedent("""\
import pytest
from plugins.{slug}.tracker import {ClassName}


def test_name():
    t = {ClassName}()
    assert t.name() == "{slug}"


def test_estimate_returns_float():
    t = {ClassName}()
    cost = t.estimate({"model": "gpt-4o", "tokens_in": 100, "tokens_out": 50})
    assert isinstance(cost, float)
"""),
}


def run(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ahy_governance scaffold",
        description="Generate a plugin scaffold for ahy-governance.",
    )
    parser.add_argument(
        "--type", required=True,
        choices=["detector", "channel", "tracker"],
        help="Plugin type to scaffold.",
    )
    parser.add_argument(
        "--name", required=True,
        help="CamelCase class name, e.g. RuleInjectionDetector.",
    )
    parser.add_argument(
        "--dir", default="plugins",
        help="Output directory (default: plugins/).",
    )
    opts = parser.parse_args(args)

    name: str = opts.name
    slug = _camel_to_snake(name)
    ptype: str = opts.type
    out_dir = Path(opts.dir) / slug

    if out_dir.exists():
        print(f"Error: {out_dir} already exists. Remove it or choose a different name.")
        return 1

    out_dir.mkdir(parents=True)
    module_base = TEMPLATES[ptype]["module"].replace(".py", "")

    # __init__.py
    (out_dir / "__init__.py").write_text(
        INIT_TEMPLATE.format(module_base=module_base, ClassName=name),
        encoding="utf-8",
    )

    # module file
    doc_title = f"{name} — {ptype} plugin for ahy-governance."
    body = TEMPLATES[ptype]["body"].format(
        ClassName=name, slug=slug, doc_title=doc_title,
    )
    (out_dir / TEMPLATES[ptype]["module"]).write_text(body, encoding="utf-8")

    # test file
    test_body = TEST_TEMPLATES[ptype].format(slug=slug, ClassName=name)
    (out_dir / f"test_{module_base}.py").write_text(test_body, encoding="utf-8")

    print(f"Created {out_dir}/")
    for f in sorted(out_dir.iterdir()):
        print(f"  {f.name}")
    print(f"\nNext: implement {name}.{TEMPLATES[ptype]['module'].split('.')[0]}() in {out_dir / TEMPLATES[ptype]['module']}")
    return 0


def _camel_to_snake(name: str) -> str:
    buf: list[str] = []
    for ch in name:
        if ch.isupper() and buf:
            buf.append("_")
        buf.append(ch.lower())
    return "".join(buf).lstrip("_")


if __name__ == "__main__":
    sys.exit(run())
