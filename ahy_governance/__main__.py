"""Entry point for ``python -m ahy_governance``."""

import sys
from pathlib import Path


def main():
    # Ensure web/ is on sys.path so server.py is importable
    _project_root = Path(__file__).resolve().parent.parent
    _web_dir = _project_root / "web"
    if str(_web_dir) not in sys.path:
        sys.path.insert(0, str(_web_dir))

    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    main()
