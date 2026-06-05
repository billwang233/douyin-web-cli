import os
from pathlib import Path

from click.testing import CliRunner
import pytest

from cli_anything.douyin_web.douyin_web_cli import cli


pytestmark = pytest.mark.skipif(
    os.environ.get("DOUYIN_E2E") != "1",
    reason="set DOUYIN_E2E=1 to run live Douyin browser tests",
)


def test_live_launch_and_state(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--home", str(tmp_path), "launch", "recommend"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(cli, ["--json", "--home", str(tmp_path), "status"])
    assert result.exit_code == 0, result.output
    assert '"status"' in result.output

    runner.invoke(cli, ["--home", str(tmp_path), "close"])
