# Hanyu HTML Deck

[中文](README.md) · [English](README.en.md)

A local-first framework for AI-generated HTML presentations. The Chinese name is 本地演示台 — "the local presentation stand".

Hanyu HTML Deck ships as both a reusable presentation template and a focused skill. The core HTML needs no install, account, or network connection. A local service adds phone prompting, remote control, source write-back, and exports.

## What it is and what it isn't

Hanyu HTML Deck gives you presentation mechanics and an authoring workflow: navigation, step animations, speaker script, notes, phone prompting, source write-back, and exports.

It is not a slide design template. There are no themes, color schemes, or ready-made layout sets. `template.html` is a runnable starting point, and its sample pages are page skeletons — the actual layout is built for each deck from its own content. If what you want is a theme or layout pack, this project does not solve that.

## Intended use

- Building HTML presentations with AI coding tools such as Codex or Claude Code.
- Keeping slides, speaker script, and revision notes in one file.
- Using a phone as a teleprompter and remote without depending on public infrastructure.
- Writing browser edits back to the original HTML with explicit safety checks.

## Feature boundary

| Feature | HTML only | Local service |
|---|:---:|:---:|
| Slide navigation, overview, presentation mode | ✓ | ✓ |
| Step animations and hover interactions | ✓ | ✓ |
| Edit script and notes in the browser | ✓ | ✓ |
| Remember panel and drawer state | ✓ | ✓ |
| Export script and copy changed notes | ✓ | ✓ |
| Phone teleprompter and remote | | ✓ |
| Write script, notes, and canvas text back to source | | ✓ |
| Export page images, PDF, and a standalone send copy | | ✓ |

The local service stays on the current LAN. It does not use a public relay or upload speaker content. Cross-network control is intentionally out of scope.

## Quick start

```bash
git clone <repository url>
cd hanyu-html-deck
python3 scripts/create_deck.py ~/Documents/my-deck
```

Open `my-deck/index.html`, update `DECK.name` and `DECK.key` near the end of the file, then replace the sample content. Double-click `启动本地演示台.command` when you need advanced features.

The core HTML works in modern browsers on macOS, Windows, and Linux. In version 0.1 the local service, launcher, and export workflow are verified on macOS only: image, PDF, and send-copy exports rely on the macOS `sips` command. On Windows and Linux, run `python3 scripts/prompter_server.py` to use phone prompting and write-back; the exports are unavailable.

## Installing the skill

The skill lets an AI coding tool build decks against this project's conventions.

- As an installed skill: place the repository (keeping `assets/` and `scripts/`) in the directory your tool reads skills from, for example `~/.claude/skills/hanyu-html-deck/`. The relative paths inside `SKILL.md` depend on that layout.
- Without installing: point the AI at `SKILL.md` in the repository and name your target directory.

When invoking it, state the content, the occasion, and the page count, and ask explicitly for the Hanyu HTML Deck skill.

## Script and notes

The bottom script panel starts collapsed to a single header row. Press `N` to expand it. Speaker scripts are plain paragraphs with no required outline structure.

Once expanded, a sidebar icon at the bottom right of the script column opens the notes drawer. Notes can hold revision requests, supporting information, or personal reminders. Closing the drawer only changes the view; it does not delete content.

Panel and drawer state are stored separately in localStorage and scoped by `DECK.key`.

The export menu includes:

- `导出讲稿`: downloads all speaker scripts as Markdown.
- `复制改动的备注`: copies only user-modified notes, grouped by page.
- `导出每页图片`: renders one PNG per page; needs the local service and Playwright.
- `导出 PDF`: captures every page, then assembles an image-based PDF.
- `导出单独发送版`: one self-contained HTML file with fonts and images inlined, notes and write-back code stripped.
- `切换为 1:1 像素`: disables canvas scaling so DOM or Figma capture tools see true 1920 × 1080 coordinates.

Hovering a menu item for about a second shows a one-line explanation.

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

- Script and note edits are written back to `index.html` automatically, about 1.5 seconds after you stop typing. There is no save button.
- A status light sits at the bottom right of the script column: green means everything is on disk, amber means some edits still live only in this browser — usually because the local service is not running. Hover it for the reason.
- Next to the light is history: the script and the notes each keep their own version timeline, and you can restore any snapshot or the original text.
- Double-click canvas text to edit it; blur writes the updated canvas back.
- Canvas writes are localhost-only. The service validates page count, structure, and unsafe markup before an atomic replacement.

## Keyboard

- `← / →`: previous page / next step or page
- `P` or `F`: presentation mode
- `O`: overview
- `N`: expand or collapse the script panel
- `R`: 1:1 pixel view
- `Esc`: leave the current mode

## Repository files

`scripts/create_deck.py` copies only the template, fonts, local service, and user documentation into a new Deck. The source repository also keeps development files that are not included in generated projects:

- `tests/` checks page-to-note alignment, separate UI state, local-network boundaries, and agreed product labels.
- `evals/` checks whether an AI agent follows the Skill when creating a Deck.
- `.github/workflows/ci.yml` runs the tests after each push.

## License

Original code, templates, and the skill use the [MIT License](LICENSE). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for bundled font and QR-generator licenses.
