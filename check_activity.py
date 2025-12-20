import os
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent

SF_FETCHER_NAME = "sf_fetcher.exe" if os.name == "nt" else "sf_fetcher"
RUST_BINARY = ROOT / "sf_fetcher" / "target" / "release" / SF_FETCHER_NAME

DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "levels_latest.json"


def _normalize_levels(items):
    """Returnér liste af {name, level} med int(level). Ignorer invalide entries."""
    levels = []
    for item in items or []:
        name = item.get("name") if isinstance(item, dict) else None
        level = item.get("level") if isinstance(item, dict) else None
        if name is None or level is None:
            continue
        try:
            levels.append({"name": name, "level": int(level)})
        except (TypeError, ValueError):
            continue
    return levels


def fetch_levels():
    """Kør Rust-programmet og få liste af {name, level}."""
    if not RUST_BINARY.exists():
        raise FileNotFoundError(
            f"Rust-binary findes ikke: {RUST_BINARY}\n"
            "Har du kørt `cargo build --release` i sf_fetcher-mappen?"
        )

    try:
        result = subprocess.run(
            [str(RUST_BINARY)],
            cwd=str(RUST_BINARY.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or ""
        raise RuntimeError(
            "Rust-program fejlede.\n"
            f"Exit code: {e.returncode}\n"
            f"STDERR:\n{stderr}"
        ) from e

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Kunne ikke parse JSON fra Rust-programmet:\n{e}\n"
            f"Output var (forkortet):\n{result.stdout[:500]}"
        ) from e

    return _normalize_levels(data)


def load_previous_levels():
    """Læs snapshot fra sidste kørsel. Returnerer dict: name -> level, eller None."""
    if not SNAPSHOT_PATH.exists():
        return None

    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    prev = {}
    for item in _normalize_levels(data):
        prev[item["name"]] = item["level"]
    return prev


def save_today_levels(levels):
    """Gem dagens snapshot (overskriver det gamle)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_PATH.open("w", encoding="utf-8") as f:
        json.dump(levels, f, ensure_ascii=False, indent=2)


def get_active_players(prev_levels, current_levels):
    """Returnér liste over spillere, der er steget i level siden sidst."""
    if not prev_levels:
        return []

    active = []
    for m in current_levels:
        name = m["name"]
        lvl_today = m["level"]

        lvl_prev = prev_levels.get(name)
        if lvl_prev is None:
            continue

        if lvl_today > lvl_prev:
            active.append(
                {"name": name, "from": lvl_prev, "to": lvl_today, "delta": lvl_today - lvl_prev}
            )
    return active


def print_top_progress_by_groups(active_players, top_n=10):
    """Print top udvikling (delta) i to grupper baseret på spillerens 'to' level."""
    active_sorted = sorted(active_players, key=lambda x: x["delta"], reverse=True)

    groups = [
        ("Level 100+", [p for p in active_sorted if p["to"] >= 100][:top_n]),
        ("Level 50-99", [p for p in active_sorted if 50 <= p["to"] < 100][:top_n]),
    ]

    for title, players in groups:
        print(f"\n=== Top {top_n} mest udviklede ({title}) ===")
        if not players:
            print("Ingen spillere i denne gruppe har udviklet sig siden sidst.")
            continue
        for i, p in enumerate(players, start=1):
            print(
                f"{i:2d}. {p['name']:<20} "
                f"{p['from']:>4} → {p['to']:<4} "
                f"(+{p['delta']})"
            )


def main():
    current_levels = fetch_levels()

    # Optional guard mod at overskrive snapshot med tom/underlig data
    if not current_levels:
        return

    prev_levels = load_previous_levels()
    save_today_levels(current_levels)

    active_players = get_active_players(prev_levels, current_levels)
    if active_players:
        print_top_progress_by_groups(active_players, top_n=10)


if __name__ == "__main__":
    main()
