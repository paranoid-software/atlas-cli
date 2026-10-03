import argparse
from datetime import date
from pathlib import Path

from atlas_cli.atlasfiles import (
    ATLAS_TOML,
    CLAUDE_SETTINGS,
    VSCODE_SETTINGS,
    plan_json_file,
    render_template,
    write_atlas_file,
)

ATLAS_FILES = {
    "CLAUDE.md": "CLAUDE.md",
    "STATUS.md": "STATUS.md",
    "BACKLOG.md": "BACKLOG.md",
    "_archived/README.md": "archived.md",
    ATLAS_TOML: "atlas.toml",
}
GITIGNORE = ".gitignore"
ATLAS_MARKERS = (ATLAS_TOML, "CLAUDE.md", "STATUS.md")


def register(subparsers) -> None:
    parser = subparsers.add_parser("init", help="create an Atlas in the current folder, named after it")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    folder = Path.cwd()
    found = [marker for marker in ATLAS_MARKERS if (folder / marker).exists()]
    if found:
        print(f"This folder is already an Atlas (found {', '.join(found)}); nothing was changed.")
        if ATLAS_TOML not in found:
            print("It predates _settings/ — bring it up to date with `atlas migrate`.")
        return 1
    try:
        plan = _plan_base_set(folder, date.today())
    except ValueError as error:
        print(f"{error}; nothing was changed.")
        return 1
    for path, (action, content) in plan.items():
        if content is not None:
            write_atlas_file(folder / path, content)
        print(f"{action} {path}")
    if plan[GITIGNORE][0] == "kept":
        print(f"Check that the existing {GITIGNORE} keeps only the Atlas's own files (see 07-sharing-an-atlas).")
    print("Next: add each source with `atlas link <name> <path>`.")
    return 0


def _plan_base_set(folder: Path, today: date) -> dict[str, tuple[str, str | None]]:
    plan = {
        path: ("created", render_template(template, name=folder.name, today=today.isoformat()))
        for path, template in ATLAS_FILES.items()
    }
    plan[CLAUDE_SETTINGS] = plan_json_file(folder / CLAUDE_SETTINGS, _complete_claude_settings)
    plan[VSCODE_SETTINGS] = plan_json_file(folder / VSCODE_SETTINGS, _complete_vscode_settings)
    if (folder / GITIGNORE).exists():
        plan[GITIGNORE] = ("kept", None)
    else:
        plan[GITIGNORE] = ("created", render_template("gitignore"))
    return plan


def _complete_claude_settings(settings: dict) -> dict:
    permissions = settings.setdefault("permissions", {})
    permissions.setdefault("allow", [])
    permissions.setdefault("additionalDirectories", [])
    return settings


def _complete_vscode_settings(settings: dict) -> dict:
    settings["git.autoRepositoryDetection"] = True
    settings.setdefault("git.scanRepositories", [])
    return settings
