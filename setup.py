"""Minimal setuptools entry so install/develop can register Windows autostart."""

from __future__ import annotations

import sys

from setuptools import setup
from setuptools.command.develop import develop
from setuptools.command.install import install


def _try_register() -> None:
    if sys.platform != "win32":
        return
    try:
        from sentence_reading.autostart import register_task

        code = register_task(quiet=False)
        if code != 0:
            print(
                "note: Windows autostart was not registered; "
                "run: python -m sentence_reading.autostart register",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001 — 설치는 성공시키고 안내만
        print(f"note: autostart skipped ({exc})", file=sys.stderr)


class InstallWithAutostart(install):
    def run(self) -> None:
        install.run(self)
        self.execute(_try_register, (), msg="Registering Windows autostart")


class DevelopWithAutostart(develop):
    def run(self) -> None:
        develop.run(self)
        self.execute(_try_register, (), msg="Registering Windows autostart")


setup(
    cmdclass={
        "install": InstallWithAutostart,
        "develop": DevelopWithAutostart,
    }
)
