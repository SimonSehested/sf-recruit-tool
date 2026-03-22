import os
import json
import subprocess
from pathlib import Path
from datetime import date

ROOT = Path(__file__).parent

SF_FETCHER_NAME = "sf_fetcher.exe" if os.name == "nt" else "sf_fetcher"
RUST_BINARY = ROOT / "sf_fetcher" / "target" / "release" / SF_FETCHER_NAME

DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "levels_latest.json"
HISTORY_DIR = DATA_DIR / "history"

MAX_HISTORY_DAYS = 8  # 8 snapshots → 7 daily deltas


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


def save_today_levels(levels):
    """Gem dagens snapshot (overskriver det gamle)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_PATH.open("w", encoding="utf-8") as f:
        json.dump(levels, f, ensure_ascii=False, indent=2)


def save_history(levels, date_str):
    """Gem dagens snapshot i history-mappen og ryd op i gamle filer."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{date_str}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(levels, f, ensure_ascii=False, indent=2)

    # Behold kun de MAX_HISTORY_DAYS nyeste filer
    history_files = sorted(HISTORY_DIR.glob("????-??-??.json"))
    for old_file in history_files[:-MAX_HISTORY_DAYS]:
        old_file.unlink()


def load_history():
    """
    Returnér en liste af name→level dicts, sorteret ældst→nyest,
    for de op til MAX_HISTORY_DAYS nyeste historiske snapshots.
    """
    if not HISTORY_DIR.exists():
        return []

    history_files = sorted(HISTORY_DIR.glob("????-??-??.json"))[-MAX_HISTORY_DAYS:]
    snapshots = []
    for f in history_files:
        with f.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        snapshot = {item["name"]: item["level"] for item in _normalize_levels(data)}
        snapshots.append(snapshot)
    return snapshots


def _median(values):
    """Beregn medianen af en liste af tal."""
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def get_median_gains(history_snapshots):
    """
    Beregn median daglig level-stigning pr. spiller over de seneste snapshots.
    history_snapshots: liste af {name→level} dicts, sorteret ældst→nyest.
    Returnerer {name: median_gain} — kun spillere med median > 0.
    """
    if len(history_snapshots) < 2:
        return {}

    # Saml daglige gains pr. spiller
    gains_per_player = {}
    for i in range(1, len(history_snapshots)):
        prev = history_snapshots[i - 1]
        curr = history_snapshots[i]
        for name, level_now in curr.items():
            level_before = prev.get(name)
            if level_before is None:
                continue
            delta = level_now - level_before
            if delta > 0:
                gains_per_player.setdefault(name, []).append(delta)

    return {
        name: _median(gains)
        for name, gains in gains_per_player.items()
        if gains
    }


def print_top_progress_by_groups(median_gains, current_levels, top_n=10):
    """Print top median-udvikling i to grupper baseret på spillerens nuværende level."""
    current_level_map = {m["name"]: m["level"] for m in current_levels}

    players = [
        {"name": name, "level": current_level_map.get(name, 0), "median": gain}
        for name, gain in median_gains.items()
        if current_level_map.get(name, 0) > 0
    ]
    players_sorted = sorted(players, key=lambda x: x["median"], reverse=True)

    groups = [
        ("Level 100+", [p for p in players_sorted if p["level"] >= 100][:top_n]),
        ("Level 50-99", [p for p in players_sorted if 50 <= p["level"] < 100][:top_n]),
    ]

    for title, group in groups:
        print(f"\n=== Top {top_n} mest udviklede ({title}) — median over de seneste dage ===")
        if not group:
            print("Ingen spillere i denne gruppe har udviklet sig.")
            continue
        for i, p in enumerate(group, start=1):
            median_str = f"+{p['median']:.1f}" if p['median'] != int(p['median']) else f"+{int(p['median'])}"
            print(
                f"{i:2d}. {p['name']:<20} "
                f"level {p['level']:<4} "
                f"(median: {median_str}/dag)"
            )


def main():
    current_levels = fetch_levels()

    if not current_levels:
        return

    today_str = date.today().isoformat()

    save_today_levels(current_levels)
    save_history(current_levels, today_str)

    history = load_history()
    if len(history) >= 2:
        median_gains = get_median_gains(history)
        if median_gains:
            print_top_progress_by_groups(median_gains, current_levels, top_n=10)


if __name__ == "__main__":
    main()
