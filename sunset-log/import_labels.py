"""One-off: bring the six evenings already in data/evenings.json into the archive.

Safe to re-run; it only fills in labels that are not there yet.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import store  # noqa: E402

DATA = os.path.join(HERE, "data", "evenings.json")


def main():
    con = store.connect()
    doc = json.load(open(DATA, encoding="utf-8"))
    have = set(store.favorites(con))
    added = 0
    for e in doc["evenings"]:
        if e["date"] in have:
            continue
        store.set_label(con, e["date"], "favorite",
                        photos=e.get("photos", []),
                        shot_time=e.get("shot_time"),
                        note=e.get("timestamp_confidence"))
        added += 1
    favs = store.favorites(con)
    if favs and not store.get_meta(con, "watch_start"):
        store.set_meta(con, "watch_start", favs[0])
    store.set_meta(con, "watch_end", max(favs) if favs else None)
    n = store.export_labels(con)
    con.commit()
    print(f"mirrored {n} label(s) to data/favorites.json (this file is committed)")
    print(f"imported {added} label(s); archive now has {len(favs)} favorites")
    print("  " + ", ".join(favs))
    print("\nNote: watch_start is set to the first favorite. Evenings before that")
    print("carry no information about your taste and are excluded from the")
    print("statistics. If you were watching before then, set it back with:")
    print("  python -c \"import store;c=store.connect();"
          "store.set_meta(c,'watch_start','2025-01-01');c.commit()\"")


if __name__ == "__main__":
    main()
