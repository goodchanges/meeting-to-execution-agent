import argparse
from pathlib import Path

from scripts.backup import copy_database


def main():
    parser = argparse.ArgumentParser(
        description="Restore a snapshot into an unused SQLite path."
    )
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    for suffix in ("-wal", "-shm", "-journal"):
        if Path(str(args.destination) + suffix).exists():
            parser.error(
                "The destination has existing SQLite sidecars. Use a fresh path."
            )
    copy_database(args.snapshot, args.destination)
    print("Restored into a new SQLite file.")


if __name__ == "__main__":
    main()
