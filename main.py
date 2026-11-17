#!/usr/bin/env python3
"""
oops — Instant AI-powered terminal crash explainer & fix generator

A lightweight CLI that diagnoses terminal errors and suggests instant fixes
using the Google Gemini API.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

# Pretty terminal output (shared across the whole tool)
console = Console()

# Where we store the user's Gemini API key
CONFIG_PATH = Path.home() / ".oops_config.json"

# Typer app — this is the CLI entry point
app = typer.Typer(
    add_completion=False,
    rich_markup_mode="rich",
    help="oops — Instant AI-powered terminal crash explainer & fix generator.",
)


# ---------------------------------------------------------------------------
# Gemini response schema (structured JSON via Pydantic)
# ---------------------------------------------------------------------------

class Diagnosis(BaseModel):
    """What Gemini must return after analyzing an error."""

    root_cause: str = Field(
        description="A crisp, maximum 2-sentence explanation of why the command failed."
    )
    fix_command: Optional[str] = Field(
        default=None,
        description="A single exact shell command to fix the error, or null if none applies.",
    )
    is_destructive: bool = Field(
        default=False,
        description=(
            "True if the fix deletes files, force-resets git, kills processes, "
            "or modifies system configs."
        ),
    )


# ---------------------------------------------------------------------------
# Config helpers — load / save the Gemini API key
# ---------------------------------------------------------------------------

def load_api_key() -> str:
    """
    Load the Gemini API key from ~/.oops_config.json.
    If the file or key is missing, ask the user and save it.
    """
    # Try reading an existing config first
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            key = data.get("gemini_api_key", "").strip()
            if key:
                return key
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable config — fall through and re-prompt
            pass

    # First run (or missing key): prompt the user securely
    console.print(
        "\n[bold yellow]Welcome to oops![/] First-time setup.\n"
        "Get a free Gemini API key at: "
        "[link=https://aistudio.google.com/apikey]https://aistudio.google.com/apikey[/]\n"
    )
    key = Prompt.ask("Enter your Gemini API key", password=True).strip()

    if not key:
        console.print("[bold red]No API key entered. Exiting.[/]")
        raise typer.Exit(code=1)

    # Save the key with restrictive permissions (owner read/write only)
    save_api_key(key)
    console.print(f"[green]API key saved to[/] {CONFIG_PATH}\n")
    return key


def save_api_key(key: str) -> None:
    """Write the API key to ~/.oops_config.json with mode 0o600."""
    CONFIG_PATH.write_text(
        json.dumps({"gemini_api_key": key}, indent=2) + "\n",
        encoding="utf-8",
    )
    # Restrict permissions so only the current user can read the file
    os.chmod(CONFIG_PATH, 0o600)


# ---------------------------------------------------------------------------
# Input modes — pipe, wrapper, and history
# ---------------------------------------------------------------------------

def get_piped_input() -> Optional[str]:
    """
    Pipe Mode: if stdin is not a TTY, read all piped error output.
    Returns the text, or None if nothing useful was piped.
    """
    if sys.stdin.isatty():
        return None

    # Read everything that was piped into us
    text = sys.stdin.read()
    if text and text.strip():
        return text
    return None


def run_command(command: str) -> tuple[int, str]:
    """
    Run a shell command and capture combined stdout + stderr.
    Returns (exit_code, combined_output).
    """
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
    )
    # Merge stdout and stderr so Gemini sees the full picture
    output = ""
    if result.stdout:
        output += result.stdout
    if result.stderr:
        if output:
            output += "\n"
        output += result.stderr
    return result.returncode, output


def parse_history_line(line: str) -> Optional[str]:
    """
    Extract the actual command from a history line.
    Handles Zsh extended history format:  : 1700000000:0;command
    Also handles plain bash history (just the command).
    """
    line = line.strip()
    if not line:
        return None

    # Zsh extended history: starts with ": " then timestamps then ";" then command
    if line.startswith(":") and ";" in line:
        # Split on the first ";" and take everything after it
        command = line.split(";", 1)[1].strip()
        return command if command else None

    # Plain bash history — the whole line is the command
    return line


def get_last_failed_command_from_history() -> Optional[str]:
    """
    History Mode: find the most recent shell command that is NOT 'oops'.
    Checks ~/.zsh_history first, then falls back to ~/.bash_history.
    """
    history_files = [
        Path.home() / ".zsh_history",
        Path.home() / ".bash_history",
    ]

    for history_path in history_files:
        if not history_path.exists():
            continue

        try:
            # Read as binary then decode loosely — history files can have
            # weird encodings or null bytes from multi-line commands
            raw = history_path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
        except OSError:
            continue

        # Walk the history from newest to oldest
        lines = text.splitlines()
        for line in reversed(lines):
            command = parse_history_line(line)
            if command is None:
                continue

            # Skip any previous oops invocations
            # (covers "oops", "oops something", "./oops", etc.)
            first_word = command.split()[0] if command.split() else ""
            if first_word in ("oops", "./oops") or command.startswith("oops "):
                continue

            return command

    return None


# ---------------------------------------------------------------------------
# AI analysis via Google Gemini
# ---------------------------------------------------------------------------

def analyze_error(api_key: str, error_output: str, failed_command: Optional[str]) -> Diagnosis:
    """
    Send the error output to Gemini and get back a structured Diagnosis.
    Only the last 6000 characters of the error are sent to stay within limits.
    """
    # Truncate long logs — keep the end, which usually has the real error
    truncated = error_output[-6000:] if len(error_output) > 6000 else error_output

    os_info = f"{platform.system()} ({platform.machine()})"
    command_info = failed_command if failed_command else "(unknown — error was piped in)"

    prompt = f"""You are an expert developer helping diagnose a terminal error.

Operating system: {os_info}
Failed command: {command_info}

Error output:
```
{truncated}
```

Explain the root cause in at most 2 crisp sentences.
If a single exact shell command can fix it, provide that command.
Set is_destructive to true if the fix deletes files, force-resets git,
kills processes, or modifies system configs. Otherwise set it to false.
If no shell command can fix this, set fix_command to null.
"""

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Diagnosis,
        ),
    )

    # response.parsed is already a validated Diagnosis instance
    diagnosis = response.parsed
    if diagnosis is None:
        # Fallback: try parsing the raw JSON text ourselves
        diagnosis = Diagnosis.model_validate_json(response.text)

    return diagnosis


# ---------------------------------------------------------------------------
# Interactive UI — show results and ask what to do
# ---------------------------------------------------------------------------

def read_from_tty(prompt_text: str) -> str:
    """
    Read a line of user input from /dev/tty so prompts still work
    even when stdin was consumed by Pipe Mode.
    Falls back to rich Prompt (normal input) if /dev/tty is unavailable.
    """
    try:
        # Open the real terminal device directly
        with open("/dev/tty", "r") as tty_in, open("/dev/tty", "w") as tty_out:
            tty_out.write(prompt_text)
            tty_out.flush()
            answer = tty_in.readline()
            return answer.strip()
    except OSError:
        # Windows or environments without /dev/tty — use normal input
        return Prompt.ask(prompt_text.rstrip(": ")).strip()


def copy_to_clipboard(text: str) -> bool:
    """
    Copy text to the system clipboard.
    Tries pbcopy (macOS), then wl-copy (Wayland), then xclip (X11).
    Returns True on success, False if no clipboard tool was found.
    """
    clipboard_tools = [
        ["pbcopy"],                          # macOS
        ["wl-copy"],                         # Linux Wayland
        ["xclip", "-selection", "clipboard"],  # Linux X11
    ]

    for tool in clipboard_tools:
        try:
            subprocess.run(
                tool,
                input=text,
                text=True,
                check=True,
                capture_output=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

    return False


def display_and_prompt(diagnosis: Diagnosis) -> None:
    """
    Show the root cause and suggested fix panels, then ask the user
    to [R]un, [C]opy, or [Q]uit.
    """
    # --- Root Cause panel (always shown) ---
    console.print()
    console.print(
        Panel(
            diagnosis.root_cause,
            title="[bold red]Root Cause[/]",
            border_style="red",
            padding=(1, 2),
        )
    )

    # --- Suggested Fix panel (only if Gemini gave us a command) ---
    if diagnosis.fix_command:
        border = "yellow" if diagnosis.is_destructive else "green"
        title_color = "yellow" if diagnosis.is_destructive else "green"
        title_extra = " [bold yellow]⚠ DESTRUCTIVE[/]" if diagnosis.is_destructive else ""

        syntax = Syntax(
            diagnosis.fix_command,
            "bash",
            theme="monokai",
            word_wrap=True,
        )
        console.print(
            Panel(
                syntax,
                title=f"[bold {title_color}]Suggested Fix[/]{title_extra}",
                border_style=border,
                padding=(1, 2),
            )
        )

        # Ask the user what to do with the fix
        console.print()
        choice = read_from_tty("[R]un fix  [C]opy fix  [Q]uit › ").upper()

        if choice.startswith("R"):
            # Warn again before running a destructive command
            if diagnosis.is_destructive:
                confirm = read_from_tty(
                    "This fix looks destructive. Type YES to confirm › "
                )
                if confirm != "YES":
                    console.print("[yellow]Cancelled.[/]")
                    return

            console.print(f"\n[dim]Running:[/] {diagnosis.fix_command}\n")
            # Run interactively so the user sees live output
            subprocess.run(diagnosis.fix_command, shell=True)

        elif choice.startswith("C"):
            if copy_to_clipboard(diagnosis.fix_command):
                console.print("[green]Fix copied to clipboard.[/]")
            else:
                console.print(
                    "[yellow]Could not find a clipboard tool "
                    "(tried pbcopy, wl-copy, xclip).[/]\n"
                    f"Here is the command to copy manually:\n"
                    f"  {diagnosis.fix_command}"
                )

        else:
            # Quit (or any unrecognized key)
            console.print("[dim]Bye.[/]")

    else:
        # No fix command — just show the diagnosis and exit
        console.print("\n[dim]No automatic fix available. See the root cause above.[/]")


# ---------------------------------------------------------------------------
# Main CLI entry point
# ---------------------------------------------------------------------------

@app.callback(
    invoke_without_command=True,
    # Let flags like -o / --flag pass through to the wrapped command
    # instead of Typer treating them as oops options.
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def main(
    ctx: typer.Context,
    command_parts: Optional[list[str]] = typer.Argument(
        None,
        help="Command to run and diagnose (Wrapper Mode). Example: oops python app.py",
    ),
) -> None:
    """
    Instant AI-powered terminal crash explainer & fix generator.

    \b
    Three ways to use oops:
      1. Pipe Mode:    python app.py 2>&1 | oops
      2. Wrapper Mode: oops python app.py
      3. History Mode: oops   (re-runs your last non-oops command)
    """
    # If the user typed a subcommand somehow, let Typer handle it
    if ctx.invoked_subcommand is not None:
        return

    # --- Step 1: Make sure we have an API key ---
    api_key = load_api_key()

    error_output: Optional[str] = None
    failed_command: Optional[str] = None

    # Merge declared args with any extra/unknown options (e.g. -o app).
    # With ignore_unknown_options, flags land in ctx.args.
    all_parts: list[str] = list(command_parts or []) + list(ctx.args)

    # --- Step 2: Decide which input mode to use ---

    # Mode A — Pipe Mode: data was piped into stdin
    piped = get_piped_input()
    if piped is not None:
        error_output = piped
        failed_command = None  # We don't know what command produced the pipe
        console.print("[dim]Pipe Mode — analyzing piped output…[/]")

    # Mode B — Wrapper Mode: user passed a command as arguments
    elif all_parts:
        # Join into a single shell command string.
        # Example: oops gcc main.c -o app  →  "gcc main.c -o app"
        failed_command = " ".join(all_parts)
        console.print(f"[dim]Wrapper Mode — running:[/] {failed_command}")

        exit_code, output = run_command(failed_command)

        if exit_code == 0:
            console.print(
                Panel(
                    f"[bold green]Command succeeded[/] (exit code 0)\n"
                    f"[dim]{failed_command}[/]",
                    border_style="green",
                    title="Success",
                )
            )
            if output.strip():
                console.print(output)
            raise typer.Exit(code=0)

        error_output = output
        if not error_output.strip():
            error_output = f"(Command exited with code {exit_code} but produced no output.)"

    # Mode C — History Mode: no args, no pipe — re-run the last command
    else:
        console.print("[dim]History Mode — looking up your last command…[/]")
        failed_command = get_last_failed_command_from_history()

        if not failed_command:
            console.print(
                "[bold red]No previous command found in shell history.[/]\n"
                "Try: [cyan]oops <your-command>[/]  or  [cyan]<cmd> 2>&1 | oops[/]"
            )
            raise typer.Exit(code=1)

        console.print(f"[dim]Re-running:[/] {failed_command}")
        exit_code, output = run_command(failed_command)

        if exit_code == 0:
            console.print(
                Panel(
                    f"[bold green]Last command succeeded on re-run[/] (exit code 0)\n"
                    f"[dim]{failed_command}[/]",
                    border_style="green",
                    title="Success",
                )
            )
            raise typer.Exit(code=0)

        error_output = output
        if not error_output.strip():
            error_output = f"(Command exited with code {exit_code} but produced no output.)"

    # --- Step 3: Send the error to Gemini ---
    with console.status("[bold cyan]Analyzing error with Gemini…[/]", spinner="dots"):
        try:
            diagnosis = analyze_error(api_key, error_output, failed_command)
        except Exception as exc:
            console.print(f"\n[bold red]Gemini API error:[/] {exc}")
            raise typer.Exit(code=1)

    # --- Step 4: Show results and let the user act ---
    display_and_prompt(diagnosis)


# ---------------------------------------------------------------------------
# Allow running as `python main.py …`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
