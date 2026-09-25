"""Tests for per-worker project configuration files."""

import json

import pytest

from planner.workers import (
    DEFAULT_WORKER,
    list_workers,
    normalize_worker,
    worker_config_path,
    worker_label,
    workers_dir,
)


class TestNormalizeWorker:
    """Tests for worker name normalization."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("pedro", "pedro"),
            ("Pedro", "pedro"),
            ("  Pedro  ", "pedro"),
            ("ana-maria", "ana-maria"),
            ("worker_2", "worker_2"),
        ],
    )
    def test_valid_names(self, raw, expected):
        assert normalize_worker(raw) == expected

    @pytest.mark.parametrize(
        "raw", ["", "  ", "../etc/passwd", "a/b", "pedro.json", "-pedro", "pe dro"]
    )
    def test_invalid_names_rejected(self, raw):
        with pytest.raises(ValueError):
            normalize_worker(raw)


class TestWorkerConfigPath:
    """Tests for resolving a worker's projects file."""

    def test_path_is_named_after_worker(self, tmp_path):
        assert worker_config_path("alice", tmp_path) == tmp_path / "workers" / "alice.json"

    def test_default_worker_when_omitted(self, tmp_path):
        expected = tmp_path / "workers" / f"{DEFAULT_WORKER}.json"
        assert worker_config_path(None, tmp_path) == expected

    def test_name_is_normalized(self, tmp_path):
        assert worker_config_path("Alice", tmp_path).name == "alice.json"

    def test_legacy_projects_json_used_for_default_worker(self, tmp_path):
        legacy = tmp_path / "projects.json"
        legacy.write_text(json.dumps({"projects": []}))
        assert worker_config_path(DEFAULT_WORKER, tmp_path) == legacy

    def test_worker_file_wins_over_legacy(self, tmp_path):
        (tmp_path / "projects.json").write_text(json.dumps({"projects": []}))
        workers_dir(tmp_path).mkdir()
        worker_file = workers_dir(tmp_path) / f"{DEFAULT_WORKER}.json"
        worker_file.write_text(json.dumps({"projects": []}))
        assert worker_config_path(DEFAULT_WORKER, tmp_path) == worker_file

    def test_legacy_not_used_for_other_workers(self, tmp_path):
        (tmp_path / "projects.json").write_text(json.dumps({"projects": []}))
        assert worker_config_path("alice", tmp_path).name == "alice.json"

    def test_invalid_worker_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            worker_config_path("../outside", tmp_path)


class TestListWorkers:
    """Tests for discovering workers."""

    def test_default_worker_always_present(self, tmp_path):
        assert list_workers(tmp_path) == [DEFAULT_WORKER]

    def test_lists_files_with_default_first(self, tmp_path):
        directory = workers_dir(tmp_path)
        directory.mkdir()
        for name in ["zoe", "alice", DEFAULT_WORKER]:
            (directory / f"{name}.json").write_text(json.dumps({"projects": []}))
        assert list_workers(tmp_path) == [DEFAULT_WORKER, "alice", "zoe"]

    def test_ignores_non_json_and_default_duplicate(self, tmp_path):
        directory = workers_dir(tmp_path)
        directory.mkdir()
        (directory / "alice.json").write_text(json.dumps({"projects": []}))
        (directory / "notes.txt").write_text("ignored")
        workers = list_workers(tmp_path)
        assert workers == [DEFAULT_WORKER, "alice"]
        assert workers.count(DEFAULT_WORKER) == 1


class TestWorkerLabel:
    """Tests for display labels."""

    @pytest.mark.parametrize(
        "worker,expected",
        [("pedro", "Pedro"), ("ana-maria", "Ana Maria"), ("worker_2", "Worker 2")],
    )
    def test_label(self, worker, expected):
        assert worker_label(worker) == expected


class TestLoadWorkerProjects:
    """Integration: load a worker's file through load_projects."""

    def test_round_trip(self, tmp_path):
        from planner.analysis import load_projects

        directory = workers_dir(tmp_path)
        directory.mkdir()
        (directory / "alice.json").write_text(
            json.dumps(
                {
                    "projects": [
                        {
                            "name": "Alice Project",
                            "end_date": "2027-01-31",
                            "remaining_days": 5,
                        }
                    ]
                }
            )
        )
        projects = load_projects(str(worker_config_path("alice", tmp_path)))
        assert [p.name for p in projects] == ["Alice Project"]
