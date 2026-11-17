# wtf — AI Error & Crash Explainer

A lightweight, open-source Python CLI that diagnoses terminal errors and suggests instant fixes using the Google Gemini API.

```
$ python broken.py 2>&1 | wtf

╭─ Root Cause ──────────────────────────────────────────╮
│ ModuleNotFoundError: 'requests' is not installed in   │
│ this Python environment.                              │
╰───────────────────────────────────────────────────────╯
╭─ Suggested Fix ───────────────────────────────────────╮
│ pip install requests                                  │
╰───────────────────────────────────────────────────────╯

[R]un fix  [C]opy fix  [Q]uit ›
```

## Requirements

- Python 3.9+
- A free [Gemini API key](https://aistudio.google.com/apikey) (BYOK — bring your own key)

## Installation

```bash
# Clone or cd into the project
cd wtf

# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Setup: shell alias

Add a permanent alias so you can type `wtf` from anywhere.

### zsh (`~/.zshrc`)

```bash
# wtf — AI Error & Crash Explainer
alias wtf='python3 /ABSOLUTE/PATH/TO/wtf/main.py'
```

Replace `/ABSOLUTE/PATH/TO/wtf` with the real path (e.g. `~/Desktop/wtf`).

Then reload your shell:

```bash
source ~/.zshrc
```

### bash (`~/.bashrc`)

```bash
alias wtf='python3 /ABSOLUTE/PATH/TO/wtf/main.py'
source ~/.bashrc
```

### First run

The first time you run `wtf`, it will securely prompt for your Gemini API key and save it to `~/.wtf_config.json` with `0600` permissions (owner-only read/write).

## Usage

`wtf` supports three input modes:

### 1. Pipe Mode

Pipe any failing command's output into `wtf`:

```bash
python app.py 2>&1 | wtf
npm run build 2>&1 | wtf
docker compose up 2>&1 | wtf
```

> Tip: `2>&1` merges stderr into stdout so the error text reaches the pipe.

### 2. Wrapper Mode

Let `wtf` run the command for you and capture the failure:

```bash
wtf python app.py
wtf "docker compose up"
wtf npm test
```

If the command succeeds (exit code 0), `wtf` prints a green success message and exits.

### 3. History Mode

Just type `wtf` with no arguments. It reads your shell history (`~/.zsh_history` or `~/.bash_history`), finds the most recent non-`wtf` command, re-runs it, and diagnoses the error:

```bash
$ python app.py          # this fails
$ wtf                    # diagnoses that failure
```

## Interactive actions

When a fix is suggested, you can:

| Key | Action |
|-----|--------|
| `R` | Run the fix command in your shell |
| `C` | Copy the fix to the clipboard (`pbcopy` / `wl-copy` / `xclip`) |
| `Q` | Quit |

Destructive fixes (file deletion, `git reset --force`, killing processes, etc.) are highlighted with a yellow warning border, and require typing `YES` before they run.

## Project layout

```
wtf/
├── main.py           # All core logic
├── requirements.txt  # Python dependencies
└── README.md         # You are here
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
