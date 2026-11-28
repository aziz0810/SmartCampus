from pathlib import Path
import sys

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Existing API tests set harmless placeholder DB variables at import time.
# Load the project's ignored local .env first so database integration tests
# still use the configured development account when the file is available.
load_dotenv(BACKEND_ROOT.parent / ".env", override=False)
