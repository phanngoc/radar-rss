# Radar RSS

Daily news aggregator that fetches RSS feeds, filters by interest topics, and generates a mobile-friendly HTML page with dynamic tab management.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![No Dependencies](https://img.shields.io/badge/dependencies-none-green)

## Features

- Fetches from 16 Vietnamese & international RSS sources (VnExpress, Tuổi Trẻ, Thanh Niên, Dân Trí, BBC, Reuters)
- 13 built-in interest topics with keyword + regex matching
- Dynamic tab UI — add/remove topics from the browser, persisted in localStorage
- Dark mode support (follows system preference)
- Mobile-friendly, works offline after generation
- macOS native notifications
- Zero external dependencies — stdlib only

## Topics

| Category | Topics |
|----------|--------|
| Politics | Iran, Mỹ, Việt Nam, Trung Quốc, Nga, Israel |
| Finance | Kinh tế, Chứng khoán, Đầu tư, Tiền tệ, Vàng, Kim loại & Hàng hóa |
| Tech | AI |

## Setup

```bash
git clone https://github.com/phanngoc/radar-rss.git
cd radar-rss
```

No dependencies to install — uses Python standard library only.

**Requirements:** Python 3.10+

## Usage

### Run once

```bash
python3 radar.py
```

This will:
1. Fetch all RSS sources
2. Filter articles into topics
3. Generate `output/index.html`
4. Open the page in your browser
5. Send a macOS notification (if enabled)

### Run daily with cron

```bash
# Edit crontab
crontab -e

# Add this line to run every day at 7am
0 7 * * * /path/to/radar-rss/daily.sh
```

Make sure `daily.sh` is executable:

```bash
chmod +x daily.sh
```

### Run without browser/notification

Set `open_browser` and `notify` to `false` in `config.json`:

```json
{
  "open_browser": false,
  "notify": false
}
```

## Configuration

Edit `config.json`:

```json
{
  "default_topics": ["Iran", "Mỹ", "Việt Nam"],
  "sources": [
    {"name": "VnExpress Thế giới", "url": "https://vnexpress.net/rss/the-gioi.rss"}
  ],
  "output_dir": "output",
  "max_articles_per_topic": 20,
  "open_browser": true,
  "notify": true
}
```

| Field | Description |
|-------|-------------|
| `default_topics` | Topics shown by default on first visit (users can customize in the UI) |
| `sources` | RSS feed URLs to fetch |
| `output_dir` | Directory for generated HTML |
| `max_articles_per_topic` | Max articles per topic section |
| `open_browser` | Auto-open browser after generation |
| `notify` | Send macOS notification |

### Add a custom RSS source

Add an entry to the `sources` array in `config.json`:

```json
{"name": "My Source", "url": "https://example.com/rss.xml"}
```

### Add a custom topic

In `radar.py`, add to `TOPIC_KEYWORDS`:

```python
TOPIC_KEYWORDS = {
    # ...
    "My Topic": ["keyword1", "keyword2", "keyword3"],
}
```

And optionally add an icon in `TOPIC_ICONS`:

```python
TOPIC_ICONS = {
    # ...
    "My Topic": "🔖",
}
```

For keywords that need word-boundary matching (to avoid false positives), add to `TOPIC_REGEX_KEYWORDS`:

```python
TOPIC_REGEX_KEYWORDS = {
    # ...
    "My Topic": [r"\bshort_word\b"],
}
```

## Project Structure

```
radar-rss/
├── radar.py        # Main script — fetch, filter, generate HTML
├── config.json     # Sources, default topics, settings
├── daily.sh        # Cron wrapper script
├── output/         # Generated HTML (gitignored)
│   └── index.html
└── README.md
```

## License

MIT
