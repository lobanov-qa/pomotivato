# Fonts

Local woff2 subsets for the "modern" skin (`html[data-skin="modern"]`).
The app is offline-first, so nothing loads from a font CDN.

| Family | Role | Files |
| --- | --- | --- |
| Golos Text | body (Cyrillic-first UI font) | golostext-{latin,cyrillic,cyrillic-ext}.woff2 |
| Unbounded | display headings | unbounded-{latin,cyrillic,cyrillic-ext}.woff2 |
| JetBrains Mono | numerals, dials, code-ish slots | jetbrainsmono-{latin,cyrillic,cyrillic-ext}.woff2 |

All three are under the SIL Open Font License 1.1; the license texts ship
next to the files (`*.OFL.txt`).

## How to regenerate

Fetch the variable-font CSS with a modern browser UA (Google Fonts serves
per-subset woff2 only to real browsers), download the latin, cyrillic and
cyrillic-ext URLs for each family and keep the `unicode-range` blocks as
they appear in `src/index.css`:

```bash
curl -sf -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36" \
  "https://fonts.googleapis.com/css2?family=Golos+Text:wght@400..700&family=Unbounded:wght@500..800&family=JetBrains+Mono:wght@400..700&display=swap"
```
