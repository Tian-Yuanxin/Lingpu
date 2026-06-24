from __future__ import annotations

import uvicorn

from .api import create_app

app = create_app()


def main() -> None:
    uvicorn.run("lingpu.__main__:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
