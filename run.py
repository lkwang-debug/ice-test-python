"""Development entrypoint; shares profile, pytest and report handling with runner."""
from runner import main

if __name__ == "__main__":
    raise SystemExit(main())
