from atlas_cli.cli import main


def test_print_the_usage(capsys):
    assert main([]) == 0
    assert "usage: atlas" in capsys.readouterr().out
