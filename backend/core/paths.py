"""Filesystem locations, independent of where the code is deployed.

The code was generated inside an Emergent container where the repository lived
at ``/app`` (so ``/app/backend``, ``/app/frontend``, ``/app/uploads``). Those
paths were hard-coded ~30 times, which broke Docker, Render and Windows runs.

``APP_ROOT`` is the repository root (the folder that contains ``backend/`` and
``frontend/``). It defaults to the real location of this checkout and can be
overridden with the ``APP_ROOT`` env var (e.g. ``/app`` in Docker).
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_ROOT = os.environ.get("APP_ROOT") or str(BACKEND_DIR.parent)
UPLOADS_ROOT = os.environ.get("UPLOADS_ROOT") or os.path.join(APP_ROOT, "uploads")
