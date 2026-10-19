import os
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Atlas",
    "GIT_AUTHOR_EMAIL": "atlas@example.com",
    "GIT_COMMITTER_NAME": "Atlas",
    "GIT_COMMITTER_EMAIL": "atlas@example.com",
}


class EphemeralAtlasContext:
    def __init__(
        self,
        git_sources: list[str],
        plain_sources: list[str] | None = None,
        local_git_sources: list[str] | None = None,
        origins: dict[str, str] | None = None,
        grouped_sources: dict[str, list[str]] | None = None,
        case_insensitive: bool = False,
    ):
        self._git_sources = list(git_sources)
        self._plain_sources = list(plain_sources or [])
        self._local_git_sources = list(local_git_sources or [])
        self._origin_overrides = dict(origins or {})
        self._grouped_sources = {group: list(children) for group, children in (grouped_sources or {}).items()}
        self._case_insensitive = case_insensitive
        self._saved_os: dict[str, object] = {}
        self.root: Path | None = None
        self.atlas: Path | None = None
        self._sources: dict[str, Path] = {}
        self._origins: dict[str, str] = {}
        self._saved_env: dict[str, str | None] = {}

    def __enter__(self):
        self.root = Path(tempfile.mkdtemp(prefix="atlas-"))
        try:
            self._set_identity()
            self._build()
            if self._case_insensitive:
                self._fold_case()
        except Exception:
            self._cleanup()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._cleanup()

    def source(self, name: str) -> Path:
        return self._sources[name]

    def origin(self, name: str) -> str:
        return self._origins[name]

    def _build(self) -> None:
        origins = self.root / "origins"
        origins.mkdir()
        for name in self._git_sources:
            bare = origins / f"{name}.git"
            self._seed_bare(bare, name)
            checkout = self.root / name
            subprocess.run(["git", "clone", "-q", str(bare), str(checkout)], check=True)
            if name in self._origin_overrides:
                url = self._origin_overrides[name]
                subprocess.run(["git", "-C", str(checkout), "remote", "set-url", "origin", url], check=True)
            self._sources[name] = checkout
            self._origins[name] = _git_output(["remote", "get-url", "origin"], checkout)
        for name in self._plain_sources:
            folder = self.root / name
            folder.mkdir()
            (folder / "README").write_text(f"{name}\n", encoding="utf-8")
            self._sources[name] = folder
        for name in self._local_git_sources:
            folder = self.root / name
            subprocess.run(["git", "init", "-q", "-b", "main", str(folder)], check=True)
            (folder / "README").write_text(f"{name}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(folder), "add", "README"], check=True)
            subprocess.run(["git", "-C", str(folder), "commit", "-q", "-m", "Start"], check=True)
            self._sources[name] = folder
        for group, children in self._grouped_sources.items():
            folder = self.root / group
            folder.mkdir()
            (folder / "README").write_text(f"{group}\n", encoding="utf-8")
            for child in children:
                bare = origins / group / f"{child}.git"
                bare.parent.mkdir(exist_ok=True)
                self._seed_bare(bare, child)
                checkout = folder / child
                subprocess.run(["git", "clone", "-q", str(bare), str(checkout)], check=True)
                self._origins[f"{group}/{child}"] = _git_output(["remote", "get-url", "origin"], checkout)
            self._sources[group] = folder
        self.atlas = self.root / "acme"
        self.atlas.mkdir()

    def _seed_bare(self, bare: Path, name: str) -> None:
        seed = self.root / f".seed-{name}"
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        (seed / "README").write_text(f"{name}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(seed), "add", "README"], check=True)
        subprocess.run(["git", "-C", str(seed), "commit", "-q", "-m", "Start"], check=True)
        subprocess.run(["git", "clone", "--bare", "-q", str(seed), str(bare)], check=True)
        shutil.rmtree(seed)

    def _set_identity(self) -> None:
        for key, value in _GIT_IDENTITY.items():
            self._saved_env[key] = os.environ.get(key)
            os.environ[key] = value

    def _restore_identity(self) -> None:
        for key, previous in self._saved_env.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        self._saved_env.clear()

    def _fold_case(self) -> None:
        folders = {self.atlas, self.atlas.resolve()}
        for call in ("stat", "lstat", "readlink", "unlink"):
            original = getattr(os, call)
            self._saved_os[call] = original
            setattr(os, call, _folding(original, folders))

    def _restore_os(self) -> None:
        for call, original in self._saved_os.items():
            setattr(os, call, original)
        self._saved_os.clear()

    def _cleanup(self) -> None:
        self._restore_os()
        self._restore_identity()
        if self.root is None or not self.root.exists():
            return
        cwd = Path.cwd()
        if cwd == self.root or cwd.is_relative_to(self.root):
            os.chdir(self.root.parent)
        shutil.rmtree(self.root)
        self.root = None


def orient_sources(atlas: Path, *names: str) -> None:
    """Give each source a filled orientation block in the orientation file's §1."""
    path = atlas / "AGENTS.md" if (atlas / "AGENTS.md").is_file() or not (atlas / "CLAUDE.md").is_file() else atlas / "CLAUDE.md"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    end = _end_of_section_one(lines)
    if end is None:
        lines.extend(["", "## 1. What lives here"])
        end = len(lines)
    blocks: list[str] = []
    for name in names:
        blocks.extend(
            [
                "",
                f"### {name} — tooling",
                f"- **Contributes:** {name} does its part.",
                "- **Stack:** Python.",
                "- **Cadence:** tagged releases.",
            ]
        )
    lines[end:end] = blocks
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _end_of_section_one(lines: list[str]) -> int | None:
    start = next((i for i, line in enumerate(lines) if line.startswith("## 1.")), None)
    if start is None:
        return None
    return next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))


def _folding(call, folders: set[Path]):
    def folded(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)):
            wanted = Path(os.fspath(path))
            if wanted.parent in folders:
                names = os.listdir(wanted.parent)
                if wanted.name not in names:
                    twin = next((name for name in names if _fold(name) == _fold(wanted.name)), None)
                    if twin is not None:
                        path = wanted.parent / twin
        return call(path, *args, **kwargs)

    return folded


def _fold(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _git_output(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()
