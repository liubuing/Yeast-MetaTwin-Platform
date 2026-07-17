from pathlib import Path

# Expose the deployed plugin package without requiring callers to mutate sys.path.
__path__.append(str(Path(__file__).resolve().parents[1] / "04_prediction_plugins" / "plugin_runtime"))
