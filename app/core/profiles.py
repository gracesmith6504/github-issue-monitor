import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).parent.parent.parent / "profiles"


@dataclass
class RepoProfile:
    name: str
    repos: list[str]
    calibration: str = ""
    architecture: str = ""
    domains: str = ""
    examples: list[dict] = field(default_factory=list)
    label_map: dict[str, str] = field(default_factory=dict)
    verdict_overrides: dict[str, str] = field(default_factory=dict)
    auto_label: bool = True


def load_profile(name: str, profiles_dir: Path | None = None) -> RepoProfile:
    directory = profiles_dir or PROFILES_DIR
    stem = name.removesuffix(".yaml").removesuffix(".yml")
    path = directory / f"{stem}.yaml"
    if not path.exists():
        path = directory / f"{stem}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {stem}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        raise ValueError(f"Profile {stem} is empty or not a mapping")
    if "repos" not in data or not data["repos"]:
        raise ValueError(f"Profile {stem} must have a non-empty 'repos' list")

    return RepoProfile(
        name=stem,
        repos=data["repos"],
        calibration=data.get("calibration", ""),
        architecture=data.get("architecture", ""),
        domains=data.get("domains", ""),
        examples=data.get("examples", []),
        label_map=data.get("label_map", {}),
        verdict_overrides=data.get("verdict_overrides", {}),
        auto_label=data.get("auto_label", True),
    )


def find_profile_for_repo(repo: str, profiles_dir: Path | None = None) -> RepoProfile | None:
    directory = profiles_dir or PROFILES_DIR
    if not directory.exists():
        return None

    repo_lower = repo.lower()
    for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        try:
            profile = load_profile(path.stem, profiles_dir=directory)
            if any(r.lower() == repo_lower for r in profile.repos):
                return profile
        except (ValueError, yaml.YAMLError) as e:
            logger.warning(f"Skipping malformed profile {path.name}: {e}")

    return None
