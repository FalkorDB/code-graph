"""Unit tests for bench.datasets.swe_bench (no network)."""

from __future__ import annotations

import pytest

from bench.datasets import swe_bench as sb


def _fake_inst(instance_id: str, repo: str = "x/y") -> sb.SweBenchInstance:
    return sb.SweBenchInstance(
        instance_id=instance_id,
        repo=repo,
        base_commit="deadbeef" * 5,
        problem_statement="fix the thing",
        test_patch="",
        fail_to_pass=["t::a"],
        pass_to_pass=["t::b"],
        environment_setup_commit="",
        version="0",
    )


def test_parse_list_field_handles_json_string_and_list():
    assert sb._parse_list_field('["a", "b"]') == ["a", "b"]
    assert sb._parse_list_field(["a", "b"]) == ["a", "b"]
    with pytest.raises(TypeError):
        sb._parse_list_field(42)


def test_sample_instances_is_deterministic():
    pool = [_fake_inst(f"id-{i}") for i in range(50)]
    a = sb.sample_instances(pool, stage="smoke")
    b = sb.sample_instances(pool, stage="smoke")
    assert [i.instance_id for i in a] == [i.instance_id for i in b]
    assert len(a) == sb.STAGE_SIZES["smoke"]


def test_sample_instances_respects_explicit_n():
    pool = [_fake_inst(f"id-{i}") for i in range(50)]
    out = sb.sample_instances(pool, stage="smoke", n=7)
    assert len(out) == 7


def test_sample_instances_clamps_to_pool_size():
    pool = [_fake_inst(f"id-{i}") for i in range(2)]
    out = sb.sample_instances(pool, stage="headline")  # asks for 37
    assert len(out) == 2


def test_repo_cache_path_uses_safe_delimiter(tmp_path):
    p = sb._repo_cache_path("astropy/astropy", tmp_path)
    assert p == tmp_path / "astropy__astropy"


def test_instance_to_task_maps_fields(tmp_path):
    inst = _fake_inst("foo")
    task = sb.instance_to_task(inst, tmp_path)
    assert task.task_id == "foo"
    assert task.repo_name == "x/y"
    assert task.repo_path == tmp_path
    assert task.problem_statement == "fix the thing"
    assert task.verify_cmd is None
