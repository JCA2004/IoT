import argparse
import os
from typing import Optional

from clothing_recognizer import recognize_clothing_item
from inventory_db import init_db, add_item

# Optional: if you added item_exists() into inventory_db.py as recommended
try:
    from inventory_db import item_exists  # type: ignore
except Exception:
    item_exists = None  # type: ignore


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def is_image_file(filename: str) -> bool:
    return filename.lower().endswith(IMAGE_EXTS)


def safe_listdir(folder: str):
    try:
        return sorted(os.listdir(folder))
    except FileNotFoundError:
        raise SystemExit(f"Folder not found: {folder!r}")
    except PermissionError:
        raise SystemExit(f"Permission denied reading folder: {folder!r}")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Import clothing images into wardrobe.db")
    parser.add_argument("--folder", default="photos", help="Folder containing clothing images (default: photos)")
    parser.add_argument("--no-dedupe", action="store_true", help="Disable deduplication check")
    parser.add_argument("--dry-run", action="store_true", help="Do not insert into DB; just print what would happen")
    args = parser.parse_args(argv)

    folder = args.folder
    dedupe_enabled = (not args.no_dedupe)

    # Ensure DB + tables exist
    init_db()

    filenames = safe_listdir(folder)
    image_files = [f for f in filenames if is_image_file(f)]

    if not image_files:
        print(f"No images found in {folder!r}. Supported extensions: {', '.join(IMAGE_EXTS)}")
        return 0

    inserted = 0
    skipped = 0
    errors = 0

    for filename in image_files:
        image_path = os.path.join(folder, filename)

        # Deduplication: skip if already in DB by image_path
        if dedupe_enabled:
            if item_exists is None:
                # item_exists() not available; dedupe can’t run
                pass
            else:
                try:
                    if item_exists(image_path):
                        print(f"[SKIP] {filename}: already in DB")
                        skipped += 1
                        continue
                except Exception as e:
                    # If dedupe fails, don’t kill the whole run
                    print(f"[WARN] {filename}: dedupe check failed ({e}). Continuing without skipping.")

        try:
            item = recognize_clothing_item(image_path)

            if not isinstance(item, dict):
                raise TypeError(f"recognize_clothing_item returned {type(item)}: {item!r}")

            # Basic required keys check (helps catch future regressions)
            required = ("label", "category", "color", "warmth", "waterproof", "formality")
            missing = [k for k in required if k not in item]
            if missing:
                raise KeyError(f"Missing keys from recognizer output: {missing}")

            if args.dry_run:
                print(f"[DRY] {filename} -> ({item['label']}, {item['category']})")
                continue

            item_id = add_item(
                label=item["label"],
                category=item["category"],
                color=item["color"],
                warmth=int(item["warmth"]),
                waterproof=int(item["waterproof"]),
                formality=int(item["formality"]),
                image_path=image_path,
            )

            print(f"[OK] {filename} -> id={item_id} ({item['label']}, {item['category']})")
            inserted += 1

        except Exception as e:
            print(f"[SKIP] {filename}: {e}")
            errors += 1

    total = len(image_files)
    print(f"Done. Inserted {inserted}/{total} items. Skipped {skipped}. Errors {errors}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())