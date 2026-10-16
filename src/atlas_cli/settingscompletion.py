from pathlib import Path


def complete_claude_settings(settings: dict) -> dict:
    permissions = settings.setdefault("permissions", {})
    permissions.setdefault("allow", [])
    permissions.setdefault("additionalDirectories", [])
    return settings


def complete_vscode_settings(settings: dict) -> dict:
    settings["git.autoRepositoryDetection"] = True
    settings.setdefault("git.scanRepositories", [])
    return settings


def add_scan_repository(name: str):
    def complete(settings: dict) -> dict:
        repositories = settings.setdefault("git.scanRepositories", [])
        if name not in repositories:
            repositories.append(name)
        return settings

    return complete


def add_directory(absolute: str, previous: Path | None = None):
    def complete(settings: dict) -> dict:
        permissions = settings.setdefault("permissions", {})
        directories = permissions.setdefault("additionalDirectories", [])
        stale = _previous_paths(previous)
        if stale:
            directories[:] = [item for item in directories if item not in stale]
        if absolute not in directories:
            directories.append(absolute)
        return settings

    return complete


def set_scan_repositories(name: str, entries: list[str]):
    """Replace a source's entries (`<name>` and `<name>/…`) with the given ones, where they were."""
    def complete(settings: dict) -> dict:
        repositories = settings.setdefault("git.scanRepositories", [])
        index = next((i for i, item in enumerate(repositories) if _belongs_to(item, name)), len(repositories))
        repositories[:] = [item for item in repositories if not _belongs_to(item, name)]
        repositories[index:index] = [entry for entry in entries if entry not in repositories]
        return settings

    return complete


def _belongs_to(item: str, name: str) -> bool:
    return item == name or item.startswith(f"{name}/")


def remove_scan_repository(name: str):
    def complete(settings: dict) -> dict:
        repositories = settings.get("git.scanRepositories")
        if isinstance(repositories, list):
            repositories[:] = [item for item in repositories if not _belongs_to(item, name)]
        return settings

    return complete


def scan_entries(name: str, repos: dict[str, str | None]) -> list[str]:
    """What the editor scans for a source: the source itself, or each nested repo of a folder of repos."""
    if repos:
        return [f"{name}/{child}" for child in sorted(repos)]
    return [name]


def remove_directories(stale: set[str]):
    def complete(settings: dict) -> dict:
        permissions = settings.get("permissions")
        directories = permissions.get("additionalDirectories") if isinstance(permissions, dict) else None
        if stale and isinstance(directories, list):
            directories[:] = [item for item in directories if item not in stale]
        return settings

    return complete


def _previous_paths(previous: Path | None) -> set[str]:
    if previous is None:
        return set()
    stale = {str(previous)}
    try:
        stale.add(str(previous.resolve()))
    except OSError:
        pass
    return stale
