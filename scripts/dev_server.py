from __future__ import annotations

import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


if __name__ == "__main__":
    stdout_log = (ROOT / "server.out.log").open("a", encoding="utf-8", buffering=1)
    stderr_log = (ROOT / "server.err.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = stdout_log
    sys.stderr = stderr_log

    try:
        import uvicorn

        uvicorn.run(
            "lingpu.api:create_app",
            factory=True,
            host="127.0.0.1",
            port=8000,
            log_level="warning",
        )
    except BaseException:
        (ROOT / "server.err.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
