import json
import sys
from pathlib import Path

# Add the 'src' directory to the Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path.resolve()))

from src.main import app

openapi_schema = app.openapi()

with open("openapi.json", "w") as f:
    json.dump(openapi_schema, f, indent=2)
