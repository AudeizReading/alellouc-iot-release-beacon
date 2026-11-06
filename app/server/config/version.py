"""
Read the version of the application from the pyproject.toml file.
"""

import tomllib
from pathlib import Path

PYPROJECT_PATH = Path(__file__).parents[2] / "pyproject.toml"


def get_app_version():
    """Read the version of the application from the pyproject.toml file."""
    with open(PYPROJECT_PATH, "rb") as stream:
        metadatas = tomllib.load(stream)

    project = metadatas.get("project")
    if project is None:
        raise ValueError("Missing 'project' section in pyproject.toml")

    version = project.get("version")
    if version is None:
        raise ValueError("Missing 'version' in 'project' section of pyproject.toml")

    return version
