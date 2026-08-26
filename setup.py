"""setuptools entry — design/138: unregister leftover Windows local-server task."""

from __future__ import annotations

import sys

from setuptools import setup
from setuptools.command.develop import develop
from setuptools.command.install import install


def _try_unregister() -> None:
    """WHY: old installs registered Ensure Server; never re-register after 138."""
    if sys.platform != "win32":
        return
    try:
        from sentence_reading.autostart import unregister_task

        unregister_task(quiet=True)
    except Exception as exc:  # noqa: BLE0001 — install must succeed
        print(f"note: autostart unregister skipped ({exc})", file=sys.stderr)


class InstallNoAutostart(install):
    def run(self) -> None:
        install.run(self)
        self.execute(_try_unregister, (), msg="Unregistering legacy Windows autostart")


class DevelopNoAutostart(develop):
    def run(self) -> None:
        develop.run(self)
        self.execute(_try_unregister, (), msg="Unregistering legacy Windows autostart")


setup(
    cmdclass={
        "install": InstallNoAutostart,
        "develop": DevelopNoAutostart,
    }
)
