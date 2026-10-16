import os
import platform

import pytest

from minisweagent.exceptions import Submitted

smol = pytest.importorskip("smol")


def smol_can_run_here() -> bool:
    """smol boots VMs on Apple Silicon macOS and on Linux with KVM."""
    if platform.system() == "Darwin":
        return platform.machine() == "arm64"
    return platform.system() == "Linux" and os.access("/dev/kvm", os.R_OK | os.W_OK)


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not smol_can_run_here(), reason="smol cannot boot a VM on this host"),
]


@pytest.fixture(scope="module")
def env():
    from minisweagent.environments.extra.smol import SmolEnvironment

    env = SmolEnvironment(image="python:3.11-slim", cwd="/tmp", env={"FOO": "bar"}, timeout=10)
    yield env
    env.cleanup()


def test_execute_merges_output_in_order_and_applies_cwd_and_env(env):
    assert env.execute({"command": "echo out; echo err >&2; pwd; echo $FOO"}) == {
        "output": "out\nerr\n/tmp\nbar\n",
        "returncode": 0,
        "exception_info": "",
    }
    assert env.execute({"command": "pwd"}, cwd="/")["output"] == "/\n"


@pytest.mark.parametrize(("command", "returncode"), [("exit 3", 3), ("false", 1), ("true", 0)])
def test_execute_returns_exit_code(env, command, returncode):
    assert env.execute({"command": command})["returncode"] == returncode


def test_timeout_is_reported_and_machine_keeps_working(env):
    output = env.execute({"command": "sleep 30"}, timeout=2)
    assert output["returncode"] == -1
    assert "timed out" in output["exception_info"]
    assert env.execute({"command": "echo alive"})["output"] == "alive\n"


def test_submission_raises_submitted(env):
    with pytest.raises(Submitted) as exc_info:
        env.execute({"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT; echo patch"})
    assert exc_info.value.messages[0]["extra"]["submission"] == "patch\n"


def test_no_terminal_type_so_tools_print_plain_output(env):
    assert env.execute({"command": 'echo "TERM=${TERM:-unset}"'})["output"] in ["TERM=unset\n", "TERM=dumb\n"]


def test_files_written_by_commands_persist_between_commands(env):
    env.execute({"command": "echo kept > /tmp/state.txt"})
    assert env.execute({"command": "cat /tmp/state.txt"})["output"] == "kept\n"
