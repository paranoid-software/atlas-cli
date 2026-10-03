import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Atlas",
    "GIT_AUTHOR_EMAIL": "atlas@example.com",
    "GIT_COMMITTER_NAME": "Atlas",
    "GIT_COMMITTER_EMAIL": "atlas@example.com",
}


class EphemeralAtlasContext:
    def __init__(self, git_sources: list[str], plain_sources: list[str] | None = None):
        self._git_sources = list(git_sources)
        self._plain_sources = list(plain_sources or [])
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
            self._sources[name] = checkout
            self._origins[name] = _git_output(["remote", "get-url", "origin"], checkout)
        for name in self._plain_sources:
            folder = self.root / name
            folder.mkdir()
            (folder / "README").write_text(f"{name}\n", encoding="utf-8")
            self._sources[name] = folder
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

    def _cleanup(self) -> None:
        self._restore_identity()
        if self.root is None or not self.root.exists():
            return
        cwd = Path.cwd()
        if cwd == self.root or cwd.is_relative_to(self.root):
            os.chdir(self.root.parent)
        shutil.rmtree(self.root)
        self.root = None


def _git_output(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()
