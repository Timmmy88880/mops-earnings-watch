# mops-earnings-watch

Mirrored snapshot of [財報觀測｜台股 Q3 財報追蹤](https://mops-earnings-watch.jazzytune16.chatgpt.site/).

- **Source URL:** https://mops-earnings-watch.jazzytune16.chatgpt.site/
- **Capture date:** 2026-11-01 (Asia/Taipei)
- **Method:** `wget --mirror --page-requisites --convert-links --adjust-extension --no-parent`, plus manual fetch of `assets/core.js` (ES module imported by `assets/app.js`, not followed by wget)

## Contents

| Path | Description |
|------|-------------|
| `index.html` | Main page |
| `assets/app.js` | Front-end app (loads data) |
| `assets/core.js` | Shared helpers (`selectRecords`, `summarize`, `toCsv`) |
| `assets/style.css` | Stylesheet |
| `assets/favicon.svg` | Favicon |
| `data/2026-q3.json` | Q3 2026 disclosure dataset fetched by the app |

Open `index.html` locally (a static server is preferred for ES modules). The app fetches `./data/2026-q3.json`.

## External (not mirrored)

- https://mopsov.twse.com.tw/mops/web/t05st01 (official MOPS)
- https://github.com/Timmmy88880/mops-earnings-tracker (source / Actions links)
