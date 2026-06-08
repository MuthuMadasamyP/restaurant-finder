from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent / "source" / "backend"
SOURCE_DIR = Path(__file__).resolve().parent / "source"
sys.path.insert(0, str(SOURCE_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from source.backend.main import app  # noqa: E402
