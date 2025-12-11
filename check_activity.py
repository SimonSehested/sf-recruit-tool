import os
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).parent

# Navn på Rust-binary afhængigt af OS
SF_FETCHER_NAME = "sf_fetcher.exe" if os.name == "nt" else "sf_fetcher"
RUST_BINARY = ROOT / "sf_fetcher" / "target" / "release" / SF_FETCHER_NAME

DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "levels_latest.json"   # snapshot fra sidste kørsel


# === HENT LEVELS FRA RUST ===

def fetch_levels():
    """Kør Rust-programmet og få liste af {name, level}."""
    if not RUST_BINARY.exists():
        raise FileNotFoundError(
            f"Rust-binary findes ikke: {RUST_BINARY}\n"
            "Har du kørt `cargo build --release` i sf_fetcher-mappen?"
        )

    print(f"[INFO] Kører Rust-binary: {RUST_BINARY}")
    result = subprocess.run(
        [str(RUST_BINARY)],
        capture_output=True,      # giver stdout/stderr som bytes
        cwd=str(RUST_BINARY.parent),
        text=False,               # VIGTIGT: ingen auto-dekodning
    )

    if result.returncode != 0:
        # prøv at vise stderr som utf-8, hvis muligt
        stderr_txt = ""
        if result.stderr:
            try:
                stderr_txt = result.stderr.decode("utf-8", errors="replace")
            except Exception:
                stderr_txt = repr(result.stderr)

        raise RuntimeError(
            "Rust-program fejlede.\n"
            f"Exit code: {result.returncode}\n"
            f"STDERR:\n{stderr_txt}"
        )

    if result.stdout is None:
        raise RuntimeError("Rust-programmet gav intet output på STDOUT.")

    try:
        stdout_txt = result.stdout.decode("utf-8")
    except UnicodeDecodeError as e:
        raise RuntimeError(
            f"Kunne ikke dekode output fra Rust som UTF-8:\n{e}\n"
            f"Raw bytes (forkortet): {result.stdout[:100]!r}"
        )

    try:
        data = json.loads(stdout_txt)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Kunne ikke parse JSON fra Rust-programmet:\n{e}\n"
            f"Output var (forkortet):\n{stdout_txt[:500]}"
        )

    levels = []
    for item in data:
        name = item.get("name")
        level = item.get("level")
        if name is None or level is None:
            continue
        levels.append({"name": name, "level": int(level)})

    print(f"[INFO] Hentede {len(levels)} spillere fra sf_fetcher")
    return levels



# === SNAPSHOT HÅNDTERING ===

def load_previous_levels():
    """Læs snapshot fra sidste kørsel.

    Returnerer dict: name -> level
    eller None hvis der ikke findes tidligere data.
    """
    if not SNAPSHOT_PATH.exists():
        print("[INFO] Intet tidligere level-snapshot fundet (første kørsel).")
        return None

    with SNAPSHOT_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    prev = {}
    for item in data:
        name = item.get("name")
        level = item.get("level")
        if name is None or level is None:
            continue
        prev[name] = int(level)

    print(f"[INFO] Indlæste tidligere snapshot med {len(prev)} spillere")
    return prev


def save_today_levels(levels):
    """Gem dagens snapshot (overskriver det gamle)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_PATH.open("w", encoding="utf-8") as f:
        json.dump(levels, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Gemte dagens level-snapshot ({len(levels)} spillere)")


# === AKTIVE SPILLERE (kun dem der er steget i level) ===

def get_active_players(prev_levels, current_levels):
    """Returnér liste over spillere, der er steget i level siden sidst.

    Hver entry: {name, from, to, delta}
    """
    if prev_levels is None:
        # Første gang scriptet kører – ingen sammenligning mulig
        print("[INFO] Første kørsel, ingen aktive spillere kan beregnes endnu.")
        return []

    active = []

    # current_levels er liste af {name, level}
    for m in current_levels:
        name = m["name"]
        lvl_today = m["level"]

        lvl_prev = prev_levels.get(name)
        if lvl_prev is None:
            # fandtes ikke sidste gang → ikke med i "forbedret sig siden sidst"
            continue

        if lvl_today > lvl_prev:
            active.append({
                "name": name,
                "from": lvl_prev,
                "to": lvl_today,
                "delta": lvl_today - lvl_prev,
            })

    print(f"[INFO] Fandt {len(active)} aktive spillere (steget i level siden sidst)")
    return active


# === MAIN ===

def main():
    # 1) Hent dagens niveauer fra Rust-programmet
    current_levels = fetch_levels()

    # 2) Indlæs sidste snapshot (hvis det findes)
    prev_levels = load_previous_levels()

    # 3) Gem dagens snapshot til næste kørsel (så det er "i går" næste gang)
    save_today_levels(current_levels)

    # 4) Find aktive spillere (dem der er steget i level)
    active_players = get_active_players(prev_levels, current_levels)

    if not active_players:
        print("\n=== Ingen spillere har udviklet sig siden sidst (eller første kørsel) ===")
        return

    # 5) Sortér efter delta (mest udviklet først)
    active_sorted = sorted(active_players, key=lambda x: x["delta"], reverse=True)

    # 6) Tag top 50
    top_50 = active_sorted[:50]

    # 7) Print pænt
    print("\n=== Top 50 mest udviklede siden i går ===")
    for i, p in enumerate(top_50, start=1):
        print(
            f"{i:2d}. {p['name']:<20} "
            f"{p['from']:>4} → {p['to']:<4} "
            f"(+{p['delta']})"
        )


if __name__ == "__main__":
    main()
