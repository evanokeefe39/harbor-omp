"""Harbor agent adapter for omp (oh-my-pi).

Harbor resolves an agent by name or by import path; this package has no agent
entry point, so the documented invocation is::

    harbor run ... --agent-import-path harbor_omp:OmpAgent

and Harbor's interpreter must be able to import this package (the same venv,
or ``uv tool install harbor --with harbor-omp``).
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

from harbor_omp.omp_agent import OmpAgent
from harbor_omp.options import LEGACY_RUN_FLAGS, OMP_PACKAGE, PINNED_OMP_VERSION, OmpOptions
from harbor_omp.options import package_spec as package_spec

__all__ = [
    "LEGACY_RUN_FLAGS",
    "OMP_PACKAGE",
    "PINNED_OMP_VERSION",
    "OmpAgent",
    "OmpOptions",
    "package_spec",
]

try:
    __version__ = _distribution_version("harbor-omp")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0.dev0"
