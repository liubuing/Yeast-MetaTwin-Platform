from pathlib import Path
import sys


_RUNTIME = Path(__file__).resolve().parents[1] / "10_generic_target_workflow" / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from executors import CobraFbaExecutor  # noqa: E402,F401
