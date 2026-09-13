"""Profile re-export shim.

Mappers do `from ..profile import ACCELERATOR_PREFIX, HOME_REGION, ...`. This
module forwards those names from the runtime `config` module, which is
populated by `cfn2lza.cli` (preferred) or by env-var autoload (legacy path
for `python -m cfn2lza.pipeline`).
"""
from __future__ import annotations

from . import config as _config

_config._autoload_from_env()


def __getattr__(name: str):
    try:
        return getattr(_config, name)
    except AttributeError:
        raise AttributeError(
            f"profile constant '{name}' not defined by active profile "
            f"'{getattr(_config, 'PROFILE_NAME', '<unloaded>')}'"
        ) from None
