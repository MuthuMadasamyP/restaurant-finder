from pathlib import Path
import sys
BACKEND_DIR = Path(__file__).resolve().parent / "source" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from backend.main import app # noqa: E402
