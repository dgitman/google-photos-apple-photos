# Photos Sync POC

A proof-of-concept Python script that compares your Apple Photos and Google Photos libraries, and archives Google Photos that no longer exist in Apple Photos.

## Requirements

- macOS (Apple Photos access requires it)
- Python 3.9+
- A Google Cloud project with the Photos Library API enabled

## Setup

### 1. Install dependencies

```bash
cd poc
pip install -r requirements.txt
```

### 2. Set up Google OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Enable the **Photos Library API**
4. Go to **APIs & Services → Credentials**
5. Create **OAuth 2.0 Client ID** → choose **Desktop app**
6. Copy your Client ID and Client Secret

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
```

### 4. Run

**Dry run (safe — no changes made):**
```bash
python sync.py --dry-run
```

**Save a full report to report.json:**
```bash
python sync.py --dry-run --report
```

**Test with a small sample first (first 100 Google photos):**
```bash
python sync.py --dry-run --limit 100
```

**Archive unmatched photos in Google Photos:**
```bash
python sync.py --archive
```

**Include low-confidence matches in archive (use with caution):**
```bash
python sync.py --archive --low-confidence
```

## How matching works

Photos are matched by **filename + capture date** (to the minute):

| Confidence | Criteria | Default action |
|---|---|---|
| High | Filename + date match exactly | Keep |
| Low | Filename matches, date within ±2 min | Review recommended |
| Unmatched | No match found | Archive in Google |

## Output example

```
Step 1: Loading Apple Photos library...
✓ Found 8,432 photos in Apple Photos

Step 2: Authenticating with Google Photos...
✓ Google Photos authenticated

Step 3: Fetching Google Photos library...
✓ Found 9,105 photos in Google Photos

Step 4: Matching photos...

Results
┌─────────────────────────────────┬───────┬──────────────────────┐
│ Category                        │ Count │ Action               │
├─────────────────────────────────┼───────┼──────────────────────┤
│ Total Google Photos             │ 9,105 │                      │
│ High confidence matches         │ 8,201 │ Keep                 │
│ Low confidence matches          │   231 │ Review recommended   │
│ Unmatched (not in Apple Photos) │   673 │ Would archive        │
└─────────────────────────────────┴───────┴──────────────────────┘

Dry run complete — no changes made.
Run with --archive to archive 673 unmatched Google photos.
```

## Important notes

- **Archiving is reversible** — archived photos remain in your Google Photos library and can be unarchived
- The script never deletes anything from Google Photos, only archives
- Always run `--dry-run` first and review `--report` output before archiving
- Google OAuth token is cached in `.google_token.json` — keep this file private
