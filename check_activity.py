import json
import subprocess
from pathlib import Path
import random
import time
from datetime import datetime

# === PATHS ===

ROOT = Path(__file__).parent

# Rust-binary der henter Hall of Fame spillerdata (din sf_fetcher)
RUST_BINARY = ROOT / "sf_fetcher" / "target" / "release" / "sf_fetcher"

# Rust-binary der sender in-game beskeder (din sf_mailer)
SF_MAILER_BINARY = ROOT / "sf_mailer" / "target" / "release" / "sf_mailer"

DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "levels_latest.json"      # snapshot fra sidste kørsel
BLACKLIST_PATH = DATA_DIR / "winner_blacklist.json"  # spillere der allerede har vundet


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
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Rust-program fejlede.\n"
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Kunne ikke parse JSON fra Rust-programmet:\n{e}\nOutput var:\n{result.stdout}"
        )

    # Forventet format: liste af objekter med "name" og "level"
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


# === BLACKLIST HÅNDTERING ===

def load_blacklist():
    """Læs blacklist over spillere, der allerede har vundet.

    Returnerer set af navne.
    """
    if not BLACKLIST_PATH.exists():
        print("[INFO] Ingen blacklist-fil fundet, starter med tom blacklist.")
        return set()

    with BLACKLIST_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    bl = set(data)
    print(f"[INFO] Indlæste blacklist med {len(bl)} navne")
    return bl


def save_blacklist(blacklist):
    """Gem blacklist (som liste af navne)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with BLACKLIST_PATH.open("w", encoding="utf-8") as f:
        json.dump(sorted(blacklist), f, ensure_ascii=False, indent=2)
    print(f"[INFO] Gemte blacklist med {len(blacklist)} navne")


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


# === VÆLG VINDERE BLANDT DEM DER HAR FORBEDRET SIG MEST ===

def choose_winner_pool(active_players, blacklist, pool_size=50):
    """
    Filtrér aktive spillere mod blacklist og lav en "top-pool".

    - Spillere i blacklist fjernes.
    - Sortér efter delta (mest forbedret først).
    - Tag de første `pool_size` (eller færre, hvis der ikke er så mange).

    Returnerer liste af kandidater til lodtrækning.
    """
    filtered = [p for p in active_players if p["name"] not in blacklist]
    print(f"[INFO] {len(filtered)} aktive spillere efter filtrering mod blacklist")

    if not filtered:
        return []

    filtered_sorted = sorted(filtered, key=lambda x: x["delta"], reverse=True)

    pool = filtered_sorted[:pool_size]
    print(f"[INFO] Kandidat-pool til lodtrækning: {len(pool)} spillere")
    return pool


def pick_winners(candidates, count=10):
    """
    Lodtrækning blandt kandidaterne.

    Hvis der er færre end `count` kandidater, tager vi bare dem alle.
    """
    if not candidates:
        print("[INFO] Ingen kandidater til lodtrækning.")
        return []

    n = min(count, len(candidates))

    winners = random.sample(candidates, k=n)
    print(f"[INFO] Trak {len(winners)} vindere blandt {len(candidates)} kandidater")
    return winners


# === RANDOM TIDER 12:00–17:00 MED MIN. 10 MIN GAP ===

def assign_random_times(winners, start_hour=12, end_hour=17, min_gap_minutes=10):
    """
    Giv hver vinder et tilfældigt tidspunkt mellem start_hour og end_hour (i hele minutter),
    med mindst `min_gap_minutes` mellem alle tider.

    Returnerer liste af:
      {name, from, to, delta, time: "HH:MM"}
    """
    if not winners:
        return []

    start_min = start_hour * 60
    end_min = end_hour * 60

    assigned = []  # liste af dicts: {"minutes": int, "player": {...}}

    for player in winners:
        # Forsøg et rimeligt antal gange at finde et tidspunkt der passer
        for _ in range(1000):
            candidate = random.randint(start_min, end_min)

            if all(abs(candidate - item["minutes"]) >= min_gap_minutes for item in assigned):
                assigned.append({"minutes": candidate, "player": player})
                break
        else:
            # Hvis vi ikke fandt et tidspunkt efter mange forsøg, stopper vi
            print("[WARN] Kunne ikke finde tid til alle vindere uden at bryde min_gap_minutes.")
            break

    # Sortér efter tidspunkt for pænt output / korrekt rækkefølge
    assigned.sort(key=lambda x: x["minutes"])

    result = []
    for item in assigned:
        minutes = item["minutes"]
        hour, minute = divmod(minutes, 60)
        time_str = f"{hour:02d}:{minute:02d}"

        p = item["player"]
        result.append({
            "name": p["name"],
            "from": p["from"],
            "to": p["to"],
            "delta": p["delta"],
            "time": time_str,
        })

    print("[INFO] Tildelte tider til vindere:")
    for r in result:
        print(f"  - {r['name']} {r['from']}→{r['to']} (+{r['delta']}), tid {r['time']}")

    return result


# === SF MAIL SENDER VIA sf_mailer ===

def send_sf_message(to, body):
    """Send in-game besked via sf_mailer-binary."""
    if not SF_MAILER_BINARY.exists():
        raise FileNotFoundError(
            f"sf_mailer-binary findes ikke: {SF_MAILER_BINARY}\n"
            "Har du kørt `cargo build --release` i sf_mailer-mappen?"
        )

    result = subprocess.run(
        [str(SF_MAILER_BINARY), to, body],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"sf_mailer fejlede for {to}.\n"
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def build_message(assignment):
    """Byg selve besked-teksten til en vinder."""
    name = assignment["name"]
    time_str = assignment["time"]
    delta = assignment["delta"]
    from_lvl = assignment["from"]
    to_lvl = assignment["to"]

    return (
        f"Guild invitation\n"
        f"Greetings {name}.\n\n"
        f"I am contacting you because your level and activity speak for themselves.\n"
        f"Our guild Spaceengineers is recruiting only strong, dedicated players who want real progress.\n\n"
        f"We are ambitious, disciplined and active every day.\n"
        f"We win attacks, we win defenses, and we rise steadily through the rankings.\n"
        f"Members who join us grow fast, because everyone contributes and everyone plays.\n\n"
        f"If you want a guild that does not waste time, that expects effort and rewards commitment, then you will fit in perfectly with us.\n\n"
        f"Should you choose to join, you must send a message to any of the officers in Spaceengineers, and they will add you to the guild.\n"
        f"If not, I respect your decision.\n\n"
        f"The invitation is open.\n\n"
    )


# === SEND MED SLEEP ===

def send_with_sleep(assignments):
    """
    Kører i ét langt run:
    - For hver vinder: vent indtil deres tid, send besked.
    - Returnerer set af navne, som vi lykkedes med at sende til.
    """
    if not assignments:
        print("[INFO] Ingen vindere at sende beskeder til.")
        return set()

    sent_successfully = set()

    # Brug runnerens aktuelle dato (typisk UTC)
    today = datetime.utcnow().date()

    schedule = []
    for a in assignments:
        hour, minute = map(int, a["time"].split(":"))
        send_dt = datetime(
            year=today.year,
            month=today.month,
            day=today.day,
            hour=hour,
            minute=minute,
        )
        schedule.append((send_dt, a))

    # Sortér efter tidspunkt
    schedule.sort(key=lambda x: x[0])

    print("[INFO] Starter send_with_sleep-løkke.")
    for send_dt, a in schedule:
        now = datetime.utcnow()
        delay = (send_dt - now).total_seconds()

        if delay > 0:
            print(
                f"[INFO] Venter {int(delay)} sekunder "
                f"før besked til {a['name']} kl {a['time']} (UTC)."
            )
            time.sleep(delay)
        else:
            # Hvis tidspunktet er passeret (fx job startede for sent),
            # sender vi med det samme.
            print(
                f"[INFO] Tidspunkt {a['time']} er allerede passeret, "
                f"sender med det samme til {a['name']}."
            )

        msg = build_message(a)
        try:
            send_sf_message(a["name"], msg)
            sent_successfully.add(a["name"])
            print(f"[INFO] Sendte besked til {a['name']} ({a['time']}).")
        except Exception as e:
            print(f"[WARN] Kunne ikke sende til {a['name']}: {e}")

    print(f"[INFO] Færdig med send_with_sleep. Lykkedes for {len(sent_successfully)} spillere.")
    return sent_successfully


# === MAIN ===

def main():
    # Midlertidig test: send KUN én besked til Poopguy
    test_name = "Poopguy"
    msg = (
        f"Guild invitation\n"
        f"Greetings Poopguy.\n\n"
        f"I am contacting you because your level and activity speak for themselves.\n"
        f"Our guild Spaceengineers is recruiting only strong, dedicated players who want real progress.\n\n"
        f"We are ambitious, disciplined and active every day.\n"
        f"We win attacks, we win defenses, and we rise steadily through the rankings.\n"
        f"Members who join us grow fast, because everyone contributes and everyone plays.\n\n"
        f"If you want a guild that does not waste time, that expects effort and rewards commitment, then you will fit in perfectly with us.\n\n"
        f"Should you choose to join, you must send a message to any of the officers in Spaceengineers, and they will add you to the guild.\n"
        f"If not, I respect your decision.\n\n"
        f"The invitation is open.\n\n"
    )

    print(f"[INFO] Sender testbesked til {test_name!r}...")
    try:
        send_sf_message(test_name, msg)
        print("[INFO] Testbesked sendt uden fejl.")
    except Exception as e:
        print(f"[ERROR] Kunne ikke sende testbesked: {e}")


if __name__ == "__main__":
    main()
