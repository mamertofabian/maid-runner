"""Version information for maid-runner package."""

from pathlib import Path


def _get_version() -> str:
    """Get version dynamically from pyproject.toml or installed package."""
    try:
        from importlib.metadata import version

        return version("maid-runner")
    except Exception:
        pass

    # Read from pyproject.toml when running from source
    try:
        import tomllib

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                return data["project"]["version"]
    except ImportError:
        # Python 3.10 fallback: Simple regex parsing
        import re

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
                if match:
                    return match.group(1)
    except Exception:
        pass

    return "0.0.0"


__version__ = _get_version()
