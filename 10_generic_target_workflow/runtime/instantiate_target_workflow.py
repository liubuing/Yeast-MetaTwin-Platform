from __future__ import annotations

import argparse
from pathlib import Path

from workflow import WorkflowValidationError, instantiate


def main() -> int:
    parser = argparse.ArgumentParser(description="Instantiate a validated generic target workspace.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        print(instantiate(args.config, args.output_dir))
    except WorkflowValidationError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
