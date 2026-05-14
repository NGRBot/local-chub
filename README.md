# Local Chub

A self-hosted web app for browsing and downloading AI character cards from [chub.ai](https://chub.ai). Character cards are PNG images with embedded JSON data — the standard format used by [SillyTavern](https://sillytavern.com) and other AI chat backends.

## What it does

- **Sync cards by author** — Enter a chub.ai username and pull down all their character cards (PNG + metadata)
- **Browse locally** — View all your downloaded cards in a paginated grid, with search/filter by name, tag, author, or title
- **Manage cards** — Delete cards, edit tags, view full character details in a lightbox, copy raw JSON, and download individual card images

## Requirements

- **Python 3.10+** with pip

## Installation

```bash
# Install dependencies
pip install flask requests Pillow
```

Dependencies explained:
- **Flask** — runs the local web server
- **requests** — talks to the chub.ai API to download cards
- **Pillow** — checks downloaded images are valid PNGs

## Running

```bash
# Start the server
python localchub.py
```

Then open **http://127.0.0.1:1401** in your browser.

The first time you open it, the page will be empty. Enter a chub.ai author name in the text field (e.g. `NG`) and click **Update cards** to start downloading.

### Command-line flags

| Flag | Description |
|------|-------------|
| `--autoupdate` | Re-sync every 60 seconds (or specify seconds, e.g. `--autoupdate 120`) |
| `--synctags` | Update local card tags when they change on chub.ai |
| `--backup` | Back up old versions of updated cards into a `backup/` directory |

Example:
```bash
python localchub.py --autoupdate 300 --synctags
```

## How it works

### The API

Chub.ai exposes a search endpoint at `https://api.chub.ai/search`. It accepts a `username` parameter to filter by creator, along with parameters like `sort`, `nsfw`, `first`, `page`, etc. Local Chub hits this endpoint, downloads the card metadata (JSON) and card image (PNG) for each result, and stores them in a `static/` folder.

### Card storage

Each card is saved as two files:

- `static/{id}.png` — The card image with embedded character data (SillyTavern "chara card" format)
- `static/{id}.json` — The API metadata (name, author path, topics/tags, timestamps)

### The web server

Flask serves a single-page UI on port 1401. The frontend is vanilla HTML/CSS/JavaScript (no build tools). When you click "Update cards", it opens a Server-Sent Events (SSE) connection to `/sync`, which streams progress updates as cards download.

## What was Changed from the Original Version

- **Empty state crash** — The original code crashed on `random.choices()` when no cards were downloaded yet (empty tag set). Fixed by checking for an empty set before sampling.
- **Author-only syncing** — Originally, "Update cards" scraped the entire chub.ai front page. Changed to require an author name, using chub.ai's `username` API filter.
- **Avatar download URL mismatch** — The avatar download URL was constructed from `card['fullPath']`, but chub.ai's CDN uses a different path (e.g. `Horny_Imp_SC` vs `Horny_Imp`) for some cards, causing 404s. Changed to use `max_res_url` from the API response, which always provides the correct URL.
- **Automatic blacklisting on download failure** — When a card's image failed to download or validate, its ID was permanently written to `blacklist.txt`, excluding it from future syncs. Changed to log the error and skip instead, so transient failures don't permanently hide cards.
- **HTTP status check for image downloads** — Added a 200 status check before writing downloaded content to a PNG file, preventing error-page HTML from being saved as a card image.
- **Crash when image download fails before the PNG is written** — `deleteCard()` tried to remove both `.json` and `.png` files during cleanup, but only `.json` existed if the HTTP request failed. Changed to remove only the `.json` in that case.
