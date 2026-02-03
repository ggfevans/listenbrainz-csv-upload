import csv
import json
import stat
import time
import argparse
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
import liblistenbrainz
from liblistenbrainz.errors import ListenBrainzAPIException, InvalidAuthTokenException
import requests

load_dotenv()

ENV_FILE = ".env"
PROGRESS_FILE = "progress.json"


def check_env_permissions():
    if not os.path.exists(ENV_FILE):
        return
    try:
        mode = os.stat(ENV_FILE).st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            print(f"WARNING: {ENV_FILE} is readable by other users. Run: chmod 600 {ENV_FILE}")
    except OSError:
        pass
BATCH_SIZE = 50


def parse_row(row):
    artist, album, track, timestamp_str = row
    dt = datetime.strptime(timestamp_str.strip(), "%d %b %Y %H:%M")
    dt = dt.replace(tzinfo=timezone.utc)
    listened_at = int(dt.timestamp())

    return liblistenbrainz.Listen(
        track_name=track.strip(),
        artist_name=artist.strip(),
        release_name=album.strip() if album.strip() else None,
        listened_at=listened_at,
        additional_info={"listening_from": "lastfm"},
    )


def read_listens(csv_path):
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for line_num, row in enumerate(reader, start=1):
            if not row or all(field.strip() == "" for field in row):
                continue
            if len(row) != 4:
                print(f"WARNING: Skipping line {line_num}: expected 4 fields, got {len(row)}")
                continue
            try:
                listen = parse_row(row)
                rows.append((line_num, listen))
            except (ValueError, IndexError) as e:
                print(f"WARNING: Skipping line {line_num}: {e}")
    rows.reverse()
    return rows


def dry_run(listens):
    total = len(listens)
    print(f"Total valid listens: {total}")

    if total == 0:
        print("No listens found.")
        return

    oldest = listens[0][1]
    newest = listens[-1][1]
    oldest_dt = datetime.fromtimestamp(oldest.listened_at, tz=timezone.utc)
    newest_dt = datetime.fromtimestamp(newest.listened_at, tz=timezone.utc)
    print(f"Date range: {oldest_dt.strftime('%d %b %Y %H:%M')} UTC  ->  {newest_dt.strftime('%d %b %Y %H:%M')} UTC")

    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Batches needed: {num_batches} (batch size: {BATCH_SIZE})")

    print("\n--- First 5 listens ---")
    for line_num, listen in listens[:5]:
        dt = datetime.fromtimestamp(listen.listened_at, tz=timezone.utc)
        album = listen.release_name or "(no album)"
        print(f"  {dt.strftime('%d %b %Y %H:%M')}  {listen.artist_name} - {listen.track_name}  [{album}]")

    print("\n--- Last 5 listens ---")
    for line_num, listen in listens[-5:]:
        dt = datetime.fromtimestamp(listen.listened_at, tz=timezone.utc)
        album = listen.release_name or "(no album)"
        print(f"  {dt.strftime('%d %b %Y %H:%M')}  {listen.artist_name} - {listen.track_name}  [{album}]")

    print(f"\nDry run complete. Run with --submit to import.")


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                data = json.load(f)
                return data.get("last_submitted_index", -1)
        except (json.JSONDecodeError, ValueError):
            print("WARNING: progress.json is corrupt. Starting from beginning.")
            return -1
    return -1


def save_progress(index):
    tmp = PROGRESS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"last_submitted_index": index}, f)
    os.replace(tmp, PROGRESS_FILE)


def submit(listens):
    token = os.getenv("LISTENBRAINZ_TOKEN")
    if not token:
        print("ERROR: LISTENBRAINZ_TOKEN environment variable not set.")
        print("Set it in your .env file or export it in your shell.")
        return

    client = liblistenbrainz.ListenBrainz()
    client.set_auth_token(token)

    last_index = load_progress()
    start_index = last_index + 1

    if start_index > 0:
        print(f"Resuming from index {start_index} ({start_index} listens already submitted)")

    total = len(listens)
    if start_index >= total:
        print("All listens have already been submitted.")
        return

    remaining = listens[start_index:]
    num_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"Submitting {len(remaining)} listens in {num_batches} batches...")

    for batch_num in range(num_batches):
        batch_start = batch_num * BATCH_SIZE
        batch_end = min(batch_start + BATCH_SIZE, len(remaining))
        batch = [listen for _, listen in remaining[batch_start:batch_end]]

        absolute_end_index = start_index + batch_end - 1

        success = False
        for attempt in range(3):
            try:
                client.submit_multiple_listens(batch)
                success = True
                break
            except InvalidAuthTokenException:
                print("ERROR: Invalid auth token. Check your LISTENBRAINZ_TOKEN.")
                save_progress(start_index + batch_start - 1 if batch_start > 0 else last_index)
                return
            except ListenBrainzAPIException as e:
                err_msg = f"API error (HTTP {e.status_code})"
                if attempt < 2:
                    wait_time = 2 ** (attempt + 1)
                    print(f"  Retry {attempt + 1}/2: {err_msg}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"ERROR: Failed batch {batch_num + 1} after 3 attempts: {err_msg}")
            except requests.exceptions.RequestException as e:
                err_msg = f"{type(e).__name__}"
                if attempt < 2:
                    wait_time = 2 ** (attempt + 1)
                    print(f"  Retry {attempt + 1}/2: {err_msg}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    print(f"ERROR: Failed batch {batch_num + 1} after 3 attempts: {err_msg}")

        if not success:
            save_progress(start_index + batch_start - 1 if batch_start > 0 else last_index)
            print(f"Progress saved. Re-run --submit to resume from batch {batch_num + 1}.")
            return

        save_progress(absolute_end_index)
        submitted_total = absolute_end_index + 1
        print(f"  Batch {batch_num + 1}/{num_batches} submitted ({submitted_total}/{total} total)")

        if batch_num < num_batches - 1:
            time.sleep(2)

    print(f"\nAll {total} listens submitted successfully!")


def main():
    parser = argparse.ArgumentParser(description="Import Last.fm CSV data into ListenBrainz")
    parser.add_argument("csv_file", help="Path to Last.fm CSV export file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Validate and preview without submitting")
    group.add_argument("--submit", action="store_true", help="Submit listens to ListenBrainz")
    args = parser.parse_args()

    check_env_permissions()

    if not os.path.isfile(args.csv_file):
        print(f"ERROR: File not found or not a regular file: {args.csv_file}")
        return

    print(f"Reading CSV from {args.csv_file}...")
    listens = read_listens(args.csv_file)
    print(f"Parsed {len(listens)} valid listens.\n")

    if args.dry_run:
        dry_run(listens)
    elif args.submit:
        submit(listens)


if __name__ == "__main__":
    main()
