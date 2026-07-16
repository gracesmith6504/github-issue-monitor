import pytest
import yaml

from app.core.profiles import load_profile, find_profile_for_repo, RepoProfile
from app.core.prompt import build_system_prompt, BASE_SYSTEM_PROMPT


def _write_profile(tmp_path, name, data):
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.dump(data))
    return path


class TestLoadProfile:
    def test_loads_valid_profile(self, tmp_path):
        _write_profile(tmp_path, "test", {
            "repos": ["org/repo"],
            "calibration": "Test calibration",
            "architecture": "Test architecture",
            "domains": "Test domains",
            "examples": [{"number": 1, "verdict": "STRETCH", "reason": "test"}],
            "label_map": {"JUMP ON IT": "good first issue"},
            "verdict_thresholds": {"JUMP ON IT": 13, "GO FOR IT": 10, "STRETCH": 7, "LONG SHOT": 5},
        })
        profile = load_profile("test", profiles_dir=tmp_path)
        assert profile.name == "test"
        assert profile.repos == ["org/repo"]
        assert profile.calibration == "Test calibration"
        assert profile.architecture == "Test architecture"
        assert profile.domains == "Test domains"
        assert len(profile.examples) == 1
        assert profile.examples[0]["number"] == 1
        assert profile.label_map == {"JUMP ON IT": "good first issue"}
        assert profile.verdict_thresholds["JUMP ON IT"] == 13

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_profile("nonexistent", profiles_dir=tmp_path)

    def test_missing_repos_raises(self, tmp_path):
        _write_profile(tmp_path, "bad", {"calibration": "no repos field"})
        with pytest.raises(ValueError, match="repos"):
            load_profile("bad", profiles_dir=tmp_path)

    def test_empty_repos_raises(self, tmp_path):
        _write_profile(tmp_path, "bad", {"repos": []})
        with pytest.raises(ValueError, match="repos"):
            load_profile("bad", profiles_dir=tmp_path)

    def test_optional_fields_default_empty(self, tmp_path):
        _write_profile(tmp_path, "minimal", {"repos": ["org/repo"]})
        profile = load_profile("minimal", profiles_dir=tmp_path)
        assert profile.calibration == ""
        assert profile.architecture == ""
        assert profile.domains == ""
        assert profile.examples == []
        assert profile.label_map == {}
        assert profile.verdict_thresholds is None
        assert profile.auto_label is True

    def test_auto_label_defaults_true(self, tmp_path):
        _write_profile(tmp_path, "noflag", {"repos": ["org/repo"]})
        profile = load_profile("noflag", profiles_dir=tmp_path)
        assert profile.auto_label is True

    def test_auto_label_false(self, tmp_path):
        _write_profile(tmp_path, "noauto", {"repos": ["org/repo"], "auto_label": False})
        profile = load_profile("noauto", profiles_dir=tmp_path)
        assert profile.auto_label is False

    def test_strips_yaml_extension(self, tmp_path):
        _write_profile(tmp_path, "test", {"repos": ["org/repo"]})
        profile = load_profile("test.yaml", profiles_dir=tmp_path)
        assert profile.name == "test"


class TestFindProfileForRepo:
    def test_matches_exact_repo(self, tmp_path):
        _write_profile(tmp_path, "myprofile", {"repos": ["org/repo"]})
        profile = find_profile_for_repo("org/repo", profiles_dir=tmp_path)
        assert profile is not None
        assert profile.name == "myprofile"

    def test_case_insensitive_match(self, tmp_path):
        _write_profile(tmp_path, "myprofile", {"repos": ["NVIDIA/OpenShell"]})
        profile = find_profile_for_repo("nvidia/openshell", profiles_dir=tmp_path)
        assert profile is not None

    def test_no_match_returns_none(self, tmp_path):
        _write_profile(tmp_path, "myprofile", {"repos": ["org/repo"]})
        result = find_profile_for_repo("other/repo", profiles_dir=tmp_path)
        assert result is None

    def test_multiple_repos_in_profile(self, tmp_path):
        _write_profile(tmp_path, "multi", {"repos": ["org/a", "org/b"]})
        assert find_profile_for_repo("org/a", profiles_dir=tmp_path) is not None
        assert find_profile_for_repo("org/b", profiles_dir=tmp_path) is not None

    def test_empty_dir_returns_none(self, tmp_path):
        result = find_profile_for_repo("org/repo", profiles_dir=tmp_path)
        assert result is None

    def test_nonexistent_dir_returns_none(self, tmp_path):
        result = find_profile_for_repo("org/repo", profiles_dir=tmp_path / "nope")
        assert result is None


class TestBuildSystemPrompt:
    def test_no_profile_returns_base(self):
        result = build_system_prompt(None)
        assert result == BASE_SYSTEM_PROMPT

    def test_profile_appends_calibration(self):
        profile = RepoProfile(name="t", repos=["x"], calibration="Custom calibration")
        result = build_system_prompt(profile)
        assert BASE_SYSTEM_PROMPT in result
        assert "Custom calibration" in result
        assert "REPOSITORY-SPECIFIC CALIBRATION" in result

    def test_profile_appends_architecture(self):
        profile = RepoProfile(name="t", repos=["x"], architecture="Arch info")
        result = build_system_prompt(profile)
        assert "ARCHITECTURE GUIDE" in result
        assert "Arch info" in result

    def test_profile_appends_examples(self):
        profile = RepoProfile(
            name="t", repos=["x"],
            examples=[{"number": 42, "scores": "SP=5 Scope=4 Fam=3", "reason": "Simple fix"}],
        )
        result = build_system_prompt(profile)
        assert "SCORING CALIBRATION EXAMPLES" in result
        assert "Issue #42" in result
        assert "SP=5" in result

    def test_profile_with_verdict_thresholds(self):
        profile = RepoProfile(
            name="t", repos=["x"],
            verdict_thresholds={"JUMP ON IT": 14, "GO FOR IT": 11, "STRETCH": 8, "LONG SHOT": 5},
        )
        result = build_system_prompt(profile)
        assert result == BASE_SYSTEM_PROMPT

    def test_empty_sections_omitted(self):
        profile = RepoProfile(name="t", repos=["x"], calibration="Only this")
        result = build_system_prompt(profile)
        assert "REPOSITORY-SPECIFIC CALIBRATION" in result
        assert "ARCHITECTURE GUIDE" not in result
        assert "DOMAIN COMPLEXITY" not in result

    def test_base_prompt_always_present(self):
        profile = RepoProfile(
            name="t", repos=["x"],
            calibration="cal", architecture="arch", domains="dom",
            examples=[{"number": 1, "verdict": "STRETCH", "reason": "r"}],
        )
        result = build_system_prompt(profile)
        assert result.startswith(BASE_SYSTEM_PROMPT)
