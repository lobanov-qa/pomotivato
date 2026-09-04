# PyInstaller recipe for the pomotivato server binary (spec 02 §9, DoD E2).
# Build from repo root:  uv run pyinstaller packaging/server.spec
# The smoke job runs the binary and polls /health; hidden imports below are
# the dynamic ones PyInstaller cannot see statically (uvicorn selects its
# loop/http implementations by string, alembic loads script_output plugins).
# hookspath=[], cipher=block_cipher — defaults suffice for this app.
block_cipher = None

a = Analysis(
    ["server_entry.py"],  # spec-relative: lives in packaging/ next to this file
    pathex=["../apps/server/src"],
    datas=[
        ("../apps/server/alembic", "alembic"),
        ("../apps/server/alembic.ini", "."),
    ],
    hiddenimports=[
        "pomotivato.main",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "aiosqlite",
        "alembic.plugins.metaclass",
        "sqlalchemy.sql.default_comparator",
    ],
    hookspath=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="pomotivato-server",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
