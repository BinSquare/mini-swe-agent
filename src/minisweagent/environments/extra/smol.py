import logging
import os
import platform
import time
from typing import Any, Literal

from pydantic import BaseModel
from smol import ConnectOptions, ExecOptions, Machine, MachineConfig, ResourceSpec

from minisweagent.exceptions import Submitted
from minisweagent.utils.serialize import recursive_merge


class SmolEnvironmentConfig(BaseModel):
    image: str
    cwd: str = "/"
    """Working directory in which to execute commands."""
    env: dict[str, str] = {}
    """Environment variables to set in the machine."""
    forward_env: list[str] = []
    """Environment variables to forward to the machine.
    Variables are only forwarded if they are set in the host environment.
    In case of conflict with `env`, the `env` variables take precedence.
    """
    timeout: int = 30
    """Timeout for executing commands in the machine."""
    target: Literal["local", "cloud"] = "local"
    """`local` runs the machine on this host; `cloud` runs it in smol cloud (needs `SMOL_CLOUD_TOKEN`)."""
    cpus: int | None = None
    memory_mb: int | None = None
    network: bool = True
    """Outbound network access, as a docker container has by default."""
    interpreter: list[str] = ["bash", "-lc"]
    """Interpreter to use to execute commands. The command is appended as its last argument."""


class SmolEnvironment:
    def __init__(self, *, config_class: type = SmolEnvironmentConfig, logger: logging.Logger | None = None, **kwargs):
        """This class executes bash commands in a [smol](https://smolmachines.com) microVM.
        See `SmolEnvironmentConfig` for keyword arguments.
        """
        self.logger = logger or logging.getLogger("minisweagent.environment")
        self.machine: Machine | None = None
        self.config = config_class(**kwargs)
        self.machine = Machine.create(
            MachineConfig(
                image=self.config.image,
                workdir=self.config.cwd,
                resources=ResourceSpec(
                    cpus=self.config.cpus, memory_mb=self.config.memory_mb, network=self.config.network
                ),
            ),
            ConnectOptions(target=self.config.target),
        )
        self.logger.info(f"Started smol machine {self.machine.name}")

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(self.config.model_dump(), platform.uname()._asdict(), kwargs)

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "environment": self.config.model_dump(mode="json"),
                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        """Execute a command in the machine and return the result as a dict."""
        command = action.get("command", "")
        assert self.machine, "Machine not started"
        env = {k: v for k in self.config.forward_env if (v := os.getenv(k)) is not None} | self.config.env
        timeout = timeout or self.config.timeout
        started = time.monotonic()
        try:
            # Merge stderr into stdout in order and drop the terminal type, as docker's exec does.
            result = self.machine.exec(
                ["sh", "-c", 'unset TERM; exec 2>&1; exec "$@"', "sh", *self.config.interpreter, command],
                ExecOptions(env=env or None, workdir=cwd or self.config.cwd, timeout=timeout),
            )
            output = {"output": result.stdout, "returncode": result.exit_code, "exception_info": ""}
            # smol reports a timeout as exit code 124; tell the model, as the docker environment does.
            if result.exit_code == 124 and time.monotonic() - started >= timeout:
                output |= {
                    "returncode": -1,
                    "exception_info": f"An error occurred while executing the command: timed out after {timeout} seconds",
                    "extra": {"exception_type": "TimeoutError", "exception": f"timed out after {timeout} seconds"},
                }
        except Exception as e:
            output = {
                "output": "",
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }
        self._check_finished(output)
        return output

    def _check_finished(self, output: dict):
        """Raises Submitted if the output indicates task completion."""
        lines = output.get("output", "").lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise Submitted(
                {
                    "role": "exit",
                    "content": submission,
                    "extra": {"exit_status": "Submitted", "submission": submission},
                }
            )

    def cleanup(self):
        """Delete the machine."""
        if getattr(self, "machine", None) is not None:  # if init fails early, machine might not be set
            self.machine.delete()
            self.machine = None

    def __del__(self):
        """Delete the machine when the object is destroyed."""
        self.cleanup()
