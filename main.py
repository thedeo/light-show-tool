import sys
import os

# Ensure the project root is on the path so `core` and `ui` are importable
sys.path.insert(0, os.path.dirname(__file__))

from core.logging_setup import configure_logging
from ui.app import run

if __name__ == "__main__":
    configure_logging()
    run()
