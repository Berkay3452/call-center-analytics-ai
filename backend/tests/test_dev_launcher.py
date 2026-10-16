"""Geliştirme başlatıcısının (`scripts/dev.py`) Docker ve ağ gerektirmeyen parçaları."""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import dev


def test_wait_until_returns_true_as_soon_as_check_passes() -> None:
    calls = {"n": 0}

    def check() -> bool:
        calls["n"] += 1
        return calls["n"] >= 3

    sleeps: list[float] = []
    assert dev.wait_until(check, timeout=10, interval=2, sleep=sleeps.append, clock=lambda: 0.0)
    assert calls["n"] == 3 and sleeps == [2, 2]


def test_wait_until_gives_up_after_timeout() -> None:
    now = {"t": 0.0}

    def sleep(seconds: float) -> None:
        now["t"] += seconds

    assert not dev.wait_until(
        lambda: False, timeout=5, interval=2, sleep=sleep, clock=lambda: now["t"]
    )
    assert now["t"] >= 5


def test_port_in_use_detects_a_listening_socket() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert dev.port_in_use(port)
    assert not dev.port_in_use(port)  # kapanınca boş


def test_ensure_env_file_copies_example_once(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("A=1\n", encoding="utf-8")

    assert dev.ensure_env_file(tmp_path) is True
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "A=1\n"

    (tmp_path / ".env").write_text("A=degisti\n", encoding="utf-8")
    assert dev.ensure_env_file(tmp_path) is False  # var olan .env ezilmez
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "A=degisti\n"


def test_ensure_env_file_exits_without_example(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        dev.ensure_env_file(tmp_path)


def test_compose_command_includes_rag_profile_only_when_asked() -> None:
    with_rag = dev.compose_command("docker", rag=True)
    without = dev.compose_command("docker", rag=False)

    assert "--profile" in with_rag and with_rag[with_rag.index("--profile") + 1] == "rag"
    assert "--profile" not in without
    assert with_rag[-2:] == ["up", "-d"] and str(dev.COMPOSE_FILE) in with_rag


def test_parse_args_defaults_start_everything() -> None:
    args = dev.parse_args([])
    assert not (args.no_rag or args.no_audio or args.no_celery or args.skip_docker or args.reset_db)

    args = dev.parse_args(["--no-rag", "--no-celery", "--skip-docker"])
    assert args.no_rag and args.no_celery and args.skip_docker


def test_fail_prints_message_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        dev.fail("Bir şey ters gitti")
    assert exc.value.code == 1
    assert "Bir şey ters gitti" in capsys.readouterr().err


@pytest.mark.skipif(os.name != "nt", reason="Windows `taskkill /T` davranışı")
def test_kill_tree_stops_child_and_grandchild() -> None:
    """Başlatıcı Ctrl+C'de uvicorn'un ve Celery'nin alt süreçlerini de kapatır."""
    code = (
        "import subprocess, sys, time;"
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "print(g.pid, flush=True); time.sleep(60)"
    )
    parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert parent.stdout is not None
    grandchild_pid = int(parent.stdout.readline())

    dev.kill_tree(parent)
    parent.wait(timeout=10)

    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {grandchild_pid}"], capture_output=True, text=True, check=False
    ).stdout
    assert str(grandchild_pid) not in out  # torun da kapandı
