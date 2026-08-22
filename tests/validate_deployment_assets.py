from __future__ import annotations

import re
import tomllib
from pathlib import Path

payload = Path("docker-compose.reranker.yml").read_text(encoding="utf-8")
assert re.search(r"image: [^\s]+@sha256:[0-9a-f]{64}$", payload, re.MULTILINE)
assert "${VLLM_IMAGE" not in payload
assert '"127.0.0.1:8000:8000"' in payload
assert "- 0.0.0.0" in payload
assert "healthcheck:" in payload

project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]
assert not any("sqliteai-vector" in dependency for dependency in project["dependencies"])
assert any("sqliteai-vector" in dependency for dependency in project["optional-dependencies"]["vector"])
