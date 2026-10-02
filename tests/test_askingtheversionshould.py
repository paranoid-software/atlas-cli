import pytest

from atlas_cli import __version__
from atlas_cli.cli import main


def test_print_the_installed_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"atlas {__version__}"
