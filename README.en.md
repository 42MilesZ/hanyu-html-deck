# Hanyu Deck

[中文](README.md) · [English](README.en.md)

A local-first framework for AI-generated HTML presentations.

Hanyu Deck ships as both a reusable presentation template and a focused skill. The core HTML needs no install, account, or network connection. A local service adds phone prompting, remote control, source write-back, and exports.

## Intended use

- Building HTML presentations with AI coding tools such as Codex or Claude Code.
- Keeping slides, speaker script, and revision notes in one file.
- Using a phone as a teleprompter and remote without depending on public infrastructure.
- Writing browser edits back to the original HTML with explicit safety checks.

## Feature boundary

| Feature | HTML only | Local service |
|---|:---:|:---:|
| Slide navigation, overview, presentation mode | ✓ | |
| Step animations and hover interactions | ✓ | |
| Edit script and notes in localStorage | ✓ | |
| Remember panel and drawer state | ✓ | |
| Export script and copy changed notes | ✓ | |
| Phone teleprompter and remote | | ✓ |
| Write script, notes, and canvas text back to source | | ✓ |
| Export page images, image PDF, and single-file HTML | | ✓ |

The local service stays on the current LAN. It does not use a public relay or upload speaker content. Cross-network control is intentionally out of scope.

## Quick start

```bash
python3 scripts/create_deck.py ~/Documents/my-deck
```

Open `my-deck/index.html`, update `DECK.name` and `DECK.key` near the end of the file, then replace the sample content. Double-click `启动 Hanyu Deck.command` when you need advanced features.

The core HTML works in modern browsers on macOS, Windows, and Linux. Version 0.1 supports the local service, launcher, and export workflow on macOS first.

## Script and notes

The bottom script panel starts collapsed to a single header row. Press `N` to expand it. Speaker scripts are plain paragraphs with no required outline structure.

The sidebar icon on the right side of the bottom header opens the notes drawer. It sits next to Save as Default and History. Notes can hold revision requests, supporting information, or personal reminders. Closing the drawer only changes the view; it does not delete content.

Panel and drawer state are stored separately in localStorage and scoped by `DECK.key`.

The export menu includes:

- `导出讲稿`: downloads all speaker scripts as Markdown.
- `复制改动的备注`: copies only user-modified notes, grouped by page.
- `原尺寸（1:1）`: disables canvas scaling so DOM or Figma capture tools see true 1920 × 1080 coordinates.

## Phone teleprompter

Start the local service, then click the phone icon in the deck. Scan the LAN QR code. The QR refreshes automatically if the network address changes.

Use the same trusted Wi-Fi by default. If no suitable Wi-Fi is available, enable the phone hotspot and connect the computer to it.

The phone starts on the speaker script. A `讲稿 / 备注` control switches views, and each page/view keeps its own scroll position. The phone can follow the computer or browse independently.

For a formal presentation, test the connection 5–10 minutes early, move forward and back two pages, disable VPNs, prevent auto-lock, and keep the phone powered.

## Local service dependencies

Phone prompting, remote control, and source write-back need Python 3 only. The QR generator is vendored.

Image and PDF exports additionally require:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

The single-file HTML export does not require Playwright. It embeds fonts and images and removes notes and source write-back code.

## Source write-back

- `存为默认` writes changed scripts or notes back to `index.html`.
- Double-click canvas text to edit it; blur writes the updated canvas back.
- Canvas writes are localhost-only. The service validates page count, structure, and unsafe markup before an atomic replacement.

## Repository files

`scripts/create_deck.py` copies only the template, fonts, local service, and user documentation into a new Deck. The source repository also keeps development files that are not included in generated projects:

- `tests/` checks page-to-note alignment, separate UI state, local-network boundaries, and agreed product labels.
- `evals/` checks whether an AI agent follows the Skill when creating a Deck.
- `.github/workflows/ci.yml` runs the tests after each push.

## License

Original code, templates, and the skill use the [MIT License](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for bundled font and QR-generator licenses.
