import shutil
import subprocess
from pathlib import Path

import pytest

from audit import config
from audit.cli import NOT_BUILT, main

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_real_target_loads() -> None:
    t = config.load("perplexity", REPO_ROOT)
    assert t.sources
    assert t.delay_seconds >= config.MIN_DELAY_SECONDS
    assert t.stage_for("https://docs.perplexity.ai/docs/agent-api/quickstart.md") == "first-use"
    assert t.stage_for("https://docs.perplexity.ai/docs/anything-else.md") == "other"


def test_unknown_surface_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "targets").mkdir()
    (tmp_path / "targets" / "bad.yaml").write_text(
        "sources:\n  - name: x\n    surface: tv-ads\n    urls: [https://example.com]\n"
    )
    with pytest.raises(config.ConfigError, match="surface"):
        config.load("bad", tmp_path)


def test_stub_commands_exit_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    for command in ("recommend", "skill", "patterns", "style", "tone"):
        assert main([command]) == 0
        assert NOT_BUILT in capsys.readouterr().out


def test_private_folder_is_never_tracked() -> None:
    """Private notes must never reach the public repo."""
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    tracked = subprocess.run(
        ["git", "ls-files", "private"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert tracked == "", f"private/ is tracked by git: {tracked}"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "private/notes.md"], cwd=REPO_ROOT
    ).returncode
    assert ignored == 0, "private/ is not in .gitignore"
