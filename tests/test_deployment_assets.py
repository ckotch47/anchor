from __future__ import annotations

import runpy


def test_deployment_assets_are_immutable_and_loopback_only() -> None:
    runpy.run_path("tests/validate_deployment_assets.py", run_name="__main__")
