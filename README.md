# Local Chub

A self-hosted web app for browsing and downloading AI character cards from [chub.ai](https://chub.ai). Character cards are PNG images with embedded JSON data — the standard format used by [SillyTavern](https://sillytavern.com) and other AI chat backends.

## What it does

- **Sync cards by author** — Enter a chub.ai username and pull down all their character cards (PNG + metadata)
- **Import cards from your machine** — Upload character card PNGs and JSON metadata files from your local computer (see Importing cards)
- **Browse locally** — View all your downloaded cards in a paginated grid, with search/filter by name, tag, author, or title
- **Manage cards** — Delete cards, edit tags, view full character details in a lightbox, copy raw JSON, and download individual card images

## Requirements

- **Python 3.10+** with pip

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
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
- `static/{id}.json` — The API metadata (name, author path, topics/tags, timestamps, etc.)

Cards synced from chub.ai use numeric IDs (e.g. `102176.png`). Cards imported from your local machine use the prefix `IMPORT{n}` (e.g. `IMPORT1.png`) to avoid ID conflicts with future chub.ai cards.

### The web server

Flask serves a single-page UI on port 1401. The frontend is vanilla HTML/CSS/JavaScript (no build tools). When you click "Update cards", it opens a Server-Sent Events (SSE) connection to `/sync`, which streams progress updates as cards download.

## Importing cards

You can also add cards that aren't from chub.ai by importing them from your local machine:

1. Click **Import Cards** near the top of the page to open a file picker
2. Select one or more `.png` or `.json` files

**PNG import** — The file is validated as a valid SillyTavern V2 character card (must contain the embedded `chara` JSON chunk). If valid, the character data is extracted and both the image and a generated metadata file are saved. PNGs without a `chara` chunk are rejected with "No JSON Data Detected."

**JSON import** — The metadata file is saved with a default grey placeholder image as the card preview. This is useful for importing metadata that was exported separately from the card image.

Imported cards are assigned IDs with the `IMPORT{n}` prefix so they never conflict with chub.ai-synced cards.

## What was Changed from the Original Version

- **Empty state crash** — The original code crashed on `random.choices()` when no cards were downloaded yet (empty tag set). Fixed by checking for an empty set before sampling.
- **Author-only syncing** — Originally, "Update cards" scraped the entire chub.ai front page. Changed to require an author name, using chub.ai's `username` API filter.
- **Avatar download URL mismatch** — The avatar download URL was constructed from `card['fullPath']`, but chub.ai's CDN uses a different path (e.g. `Horny_Imp_SC` vs `Horny_Imp`) for some cards, causing 404s. Changed to use `max_res_url` from the API response, which always provides the correct URL.
- **Automatic blacklisting on download failure** — When a card's image failed to download or validate, its ID was permanently written to `blacklist.txt`, excluding it from future syncs. Changed to log the error and skip instead, so transient failures don't permanently hide cards.
- **HTTP status check for image downloads** — Added a 200 status check before writing downloaded content to a PNG file, preventing error-page HTML from being saved as a card image.
- **Crash when image download fails before the PNG is written** — `deleteCard()` tried to remove both `.json` and `.png` files during cleanup, but only `.json` existed if the HTTP request failed. Changed to remove only the `.json` in that case.
- **Forked cards missing from author syncs** — The chub.ai search API excludes forked cards by default unless `include_forks=true` is passed. Added this parameter so authors who fork their own cards (or have forked variants) don't have missing cards during sync.
- **Local card import** — Added an "Import Cards" button that lets you upload `.png` and `.json` files from your local machine. PNGs are validated for the SillyTavern V2 `chara` chunk before importing. Imported cards use `IMPORT{n}` IDs to avoid collision with chub.ai's numeric IDs.

### Editing card data

When you open a card in the lightbox (click the image or name), the character data from the embedded V2 card is rendered as editable form controls:

- **Name** — shown at the top; editable textarea
- **Simple text fields** (description, first message, personality, scenario, creator notes, system prompt, etc.) — textareas
- **Tags** — comma-separated text input
- **Alternate greetings** — individual textareas, one per greeting
- **Character book** — read-only display to prevent accidental corruption

The following fields are present in the card data but are not shown in the editor: `avatar`, `character_version`, `creator`, and `extensions` (they are preserved as-is during save).

Click **Save** at the bottom of the lightbox to write the changes directly into the PNG's embedded `chara` chunk. The image data is preserved exactly — only the metadata chunk is replaced. Click **Cancel** to close without saving.

The spec requires that "optional properties must never be destroyed if already in the data" — hidden or complex fields are preserved as-is during save.
