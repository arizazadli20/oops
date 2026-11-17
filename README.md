# oops

**Instant AI-powered terminal crash explainer & fix generator powered by Google Gemini.**

When a command blows up in your terminal, run `oops` — it explains the root cause and suggests an exact fix you can run, copy, or dismiss.

```
$ python broken.py 2>&1 | oops

╭─ Root Cause ──────────────────────────────────────────╮
│ ModuleNotFoundError: 'requests' is not installed in   │
│ this Python environment.                              │
╰───────────────────────────────────────────────────────╯
╭─ Suggested Fix ───────────────────────────────────────╮
│ pip install requests                                  │
╰───────────────────────────────────────────────────────╯

[R]un fix  [C]opy fix  [Q]uit ›
```

## Features

- **Three input modes** — Pipe, Wrapper, and History
- **Structured Gemini analysis** — crisp root cause + exact shell fix via `gemini-2.5-flash`
- **Interactive actions** — `[R]`un, `[C]`opy, or `[Q]`uit
- **Destructive-fix warnings** — yellow border + `YES` confirm before risky commands
- **Zero-cost BYOK** — your Gemini key stays local in `~/.oops_config.json` (`0600`)

## Requirements

- Python 3.9+
- A free [Gemini API key](https://aistudio.google.com/apikey)

## Installation

```bash
# Clone the repo
git clone https://github.com/arizazadli20/oops.git
cd oops

# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Setup: global alias (`~/.zshrc`)

Add a permanent alias so you can type `oops` from anywhere:

```bash
# oops — AI terminal crash explainer
alias oops='python3 /ABSOLUTE/PATH/TO/oops/main.py'
```

Replace `/ABSOLUTE/PATH/TO/oops` with the real path to where you cloned the repo.

Then reload your shell:

```bash
source ~/.zshrc
```

**Tip (macOS Zsh):** add this so shell history updates immediately after a command fails — History Mode depends on it:

```bash
setopt INC_APPEND_HISTORY
```

### First run

The first time you run `oops`, it securely prompts for your Gemini API key and saves it to `~/.oops_config.json` with `0600` permissions (owner-only read/write).

## Usage

### 1. History Mode

Fail a command, then just type `oops` — it re-runs your last non-`oops` command and diagnoses it:

```bash
$ python app.py          # this fails
$ oops                   # diagnoses that failure
```

### 2. Pipe Mode

Pipe any failing command's output into `oops`:

```bash
python app.py 2>&1 | oops
npm run build 2>&1 | oops
docker compose up 2>&1 | oops
```

> Tip: `2>&1` merges stderr into stdout so the error text reaches the pipe.

### 3. Wrapper Mode

Let `oops` run the command for you (flags like `-o` are passed through):

```bash
oops python app.py
oops "docker compose up"
oops gcc main.c -o app
oops npm test
```

If the command succeeds (exit code 0), `oops` prints a green success message and exits.

## Interactive actions

When a fix is suggested:

| Key | Action |
|-----|--------|
| `R` | **Run** the fix command in your shell |
| `C` | **Copy** the fix to the clipboard (`pbcopy` / `wl-copy` / `xclip`) |
| `Q` | **Quit** |

Destructive fixes (file deletion, `git reset --force`, killing processes, etc.) get a yellow warning border and require typing `YES` before they run.

## Project layout

```
oops/
├── main.py           # All core logic
├── requirements.txt  # Python dependencies
├── LICENSE           # MIT
├── .gitignore
└── README.md
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `google-genai` | Gemini API client (`gemini-2.5-flash`) |
| `typer` | CLI argument parsing |
| `rich` | Panels, syntax highlighting, spinners |
| `pydantic` | Structured Gemini response schema |

## License

MIT — free to use, modify, and share.
