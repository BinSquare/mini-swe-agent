# Smol

!!! note "Smol Environment class"

    - [Read on GitHub](https://github.com/swe-agent/mini-swe-agent/blob/main/src/minisweagent/environments/extra/smol.py)
    - Runs locally on macOS Apple Silicon or Linux with KVM; smol cloud needs a `SMOL_CLOUD_TOKEN`

    ??? note "Full source code"

        ```python
        --8<-- "src/minisweagent/environments/extra/smol.py"
        ```

::: minisweagent.environments.extra.smol

This environment executes commands in [smol](https://smolmachines.com) microVMs using the [smolmachines](https://pypi.org/project/smolmachines/) SDK. Each task gets its own VM, booted from the task's container image.

## Setup

1. Install the dependencies:
   ```bash
   pip install "mini-swe-agent[smol]"
   ```

2. For smol cloud instead of this host, set a token and `target: cloud`:
   ```bash
   export SMOL_CLOUD_TOKEN="your-smol-cloud-token"
   ```

## Usage

Run mini-swe-agent like with any other environment:
```
mini-extra swebench \
    --subset verified \
    --split test \
    --workers 8 \
    --environment-class smol
```

It can be specified both through cli parameter or by setting `environment_class` to `smol` in your swebench.yaml config

{% include-markdown "../../_footer.md" %}
