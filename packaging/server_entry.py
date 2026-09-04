"""PyInstaller entrypoint: run the packaged server on UVICORN_* settings.

Kept trivial on purpose — all real wiring is create_app(); packaging bugs
should surface in the bundle, not in entry cleverness.
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "pomotivato.main:app",
        host=os.environ.get("POMOTIVATO_HOST", "127.0.0.1"),
        port=int(os.environ.get("POMOTIVATO_PORT", "8000")),
        workers=1,  # single-user desktop: FSM registry lives in this process
    )
