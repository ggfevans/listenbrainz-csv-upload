# lastfm-to-listenbrainz

A Python script to import your Last.fm listening history into [ListenBrainz](https://listenbrainz.org) from a CSV export.

## Why this exists

ListenBrainz has a built-in Last.fm import feature, but at the time of writing it wasn't working reliably. Rather than wait for a fix, I exported my Last.fm history to CSV using [lastfm-to-csv](https://github.com/benfoxall/lastfm-to-csv) and wrote this script to batch-submit the listens via the ListenBrainz API.

It's simple, it worked for ~97k listens spanning 13 years, and it might work for you too.

## Getting your CSV

Use [lastfm-to-csv](https://github.com/benfoxall/lastfm-to-csv) to export your Last.fm scrobble history. The expected CSV format is four columns with no header row:

```
Artist,Album,Track,Timestamp
```

Example:

```
Radiohead,OK Computer,Paranoid Android,15 Jun 2007 22:30
```

## Setup

Requires Python 3.7+.

```bash
pip install -r requirements.txt
```

Copy the example environment file and add your [ListenBrainz user token](https://listenbrainz.org/settings/):

```bash
cp .env.example .env
```

Then edit `.env` and replace `your-token-here` with your actual token.

## Usage

**Dry run** -- validate your CSV and preview what will be submitted:

```bash
python import_lb.py your_export.csv --dry-run
```

**Submit** -- send listens to ListenBrainz:

```bash
python import_lb.py your_export.csv --submit
```

The script tracks progress in `progress.json`. If it's interrupted for any reason, re-run the same `--submit` command and it will resume where it left off.

## Disclaimer

This software is provided **as-is**, with no warranty of any kind. It worked for my use case but your mileage may vary. Back up your data, run `--dry-run` first, and review the output before submitting. I'm not responsible for any data loss, duplicate scrobbles, or other issues that may arise from using this script.

## AI disclosure

This script was built with the assistance of [Claude](https://claude.ai) (Anthropic). The approach, architecture, and code were developed collaboratively between a human and an AI in a single session.

## License

MIT -- see [LICENSE](LICENSE).
