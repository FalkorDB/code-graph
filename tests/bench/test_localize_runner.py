"""Offline unit tests for the LocAgent-style localization runner.

These guard the two bugs found during the live smoke run:
  1. The parser must read ONLY the agent's own output (assistant/exit/
     submission), never the example sentinel embedded in the user prompt.
  2. Scoring (recall / Acc@k / MRR) must follow the LocAgent definition
     where Acc@k means "all gold files recovered within top-k".
"""
from __future__ import annotations

from bench.runners.localize_runner import (
    SENTINEL,
    parse_prediction,
    score_localization,
)


def _traj(messages, submission=None):
    info = {}
    if submission is not None:
        info["submission"] = submission
    return {"messages": messages, "info": info}


def test_parser_ignores_example_in_user_prompt():
    """The instance prompt contains an EXAMPLE sentinel; it must be skipped."""
    user_prompt = (
        "Name the files that must change. End with a line like:\n"
        f'{SENTINEL} ["pkg/module/foo.py","pkg/other.py"]\n'
    )
    assistant = (
        "I investigated the code base.\n"
        f'{SENTINEL} ["app/real_target.py","app/helper.py"]'
    )
    traj = _traj(
        [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant},
        ]
    )
    pred, err, _ = parse_prediction(traj)
    assert err is False
    assert pred == ["app/real_target.py", "app/helper.py"]
    # the example files must never leak in
    assert "pkg/module/foo.py" not in pred


def test_parser_reads_submission_field():
    sub = f'{SENTINEL} ["pkg/b.py"]'
    traj = _traj(
        [
            {"role": "user", "content": f'{SENTINEL} ["example/x.py"]'},
        ],
        submission=sub,
    )
    pred, err, _ = parse_prediction(traj)
    assert err is False
    assert pred == ["pkg/b.py"]


def test_parser_uses_last_sentinel_in_agent_text():
    assistant = (
        f'{SENTINEL} ["first/guess.py"]\n'
        "...reconsidered...\n"
        f'{SENTINEL} ["final/answer.py"]'
    )
    traj = _traj([{"role": "assistant", "content": assistant}])
    pred, err, _ = parse_prediction(traj)
    assert err is False
    assert pred == ["final/answer.py"]


def test_parser_missing_sentinel_is_error():
    traj = _traj([{"role": "assistant", "content": "no answer here"}])
    pred, err, _ = parse_prediction(traj)
    assert err is True
    assert pred == []


def test_parser_normalizes_diff_prefixes_and_dotslash():
    # git-diff style `a/`,`b/` prefixes are stripped; `./` is stripped.
    assistant = f'{SENTINEL} ["a/django/x.py", "./sympy/y.py"]'
    traj = _traj([{"role": "assistant", "content": assistant}])
    pred, err, _ = parse_prediction(traj)
    assert err is False
    assert pred == ["django/x.py", "sympy/y.py"]


def test_score_all_found_and_acc_at_k():
    gold = ["pkg/a.py", "pkg/b.py"]
    # both gold present but need top-2 -> acc@1 False, acc@3 True
    pred = ["pkg/a.py", "pkg/b.py"]
    s = score_localization(pred, gold)
    assert s["file_recall"] == 1.0
    assert s["file_all_found"] is True
    assert s["acc_at_1"] is False
    assert s["acc_at_3"] is True
    assert s["acc_at_5"] is True
    assert s["file_mrr"] == 1.0


def test_score_partial_recall():
    gold = ["pkg/a.py", "pkg/b.py"]
    pred = ["pkg/a.py", "pkg/wrong.py"]
    s = score_localization(pred, gold)
    assert s["file_recall"] == 0.5
    assert s["file_all_found"] is False
    assert s["acc_at_5"] is False
    assert s["file_mrr"] == 1.0  # first prediction is gold


def test_score_mrr_second_position():
    gold = ["pkg/b.py"]
    pred = ["pkg/wrong.py", "pkg/b.py"]
    s = score_localization(pred, gold)
    assert s["file_mrr"] == 0.5
    assert s["acc_at_1"] is False
    assert s["acc_at_3"] is True


def test_score_empty_prediction():
    s = score_localization([], ["pkg/a.py"])
    assert s["file_recall"] == 0.0
    assert s["file_all_found"] is False
    assert s["file_mrr"] == 0.0


def test_safe_env_kills_pipe_holding_grandchild_promptly():
    """The exact deadlock: a command backgrounds a child that keeps the stdout
    pipe open and sleeps far longer than the timeout. The stock
    subprocess.run(timeout=) would block in communicate(); SafeLocalEnvironment
    must return promptly with a timeout marker.
    """
    import time as _t

    from bench.runners.localize_runner import SafeLocalEnvironment

    env = SafeLocalEnvironment(cwd="/tmp", env={}, timeout=2)
    # `sleep 60 &` inherits stdout; parent echoes then exits but the child
    # holds the pipe open for 60s.
    started = _t.time()
    out = env.execute({"command": "sleep 60 & echo started; sleep 60"})
    elapsed = _t.time() - started
    assert elapsed < 15, f"did not reap promptly (took {elapsed:.1f}s)"
    assert out["returncode"] == -1
    assert "timed out" in out["output"]

def test_timeout_retry_model_interrupts_stall_then_succeeds():
    """A model whose query blocks past the per-call timeout must be interrupted
    by SIGALRM and retried; once a call returns quickly the wrapper yields it."""
    import time as _t

    from bench.runners.localize_runner import TimeoutRetryModel

    class FlakyModel:
        def __init__(self):
            self.calls = 0
            self.cost = 1.23  # attribute that must be delegated

        def query(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                _t.sleep(30)  # stall: SIGALRM must interrupt this
            return {"role": "assistant", "content": "ok"}

    inner = FlakyModel()
    wrapped = TimeoutRetryModel(inner, per_call_timeout=1, retries=2)
    started = _t.time()
    out = wrapped.query([{"role": "user", "content": "hi"}])
    elapsed = _t.time() - started
    assert out["content"] == "ok"
    assert inner.calls == 2  # first stalled+interrupted, second succeeded
    assert elapsed < 10, f"did not interrupt the stall promptly ({elapsed:.1f}s)"
    assert wrapped.cost == 1.23  # delegation works


def test_timeout_retry_model_raises_after_exhausting_retries():
    import time as _t

    from bench.runners.localize_runner import TimeoutRetryModel

    class DeadModel:
        def query(self, messages, **kwargs):
            _t.sleep(30)

    wrapped = TimeoutRetryModel(DeadModel(), per_call_timeout=1, retries=1)
    started = _t.time()
    try:
        wrapped.query([{"role": "user", "content": "hi"}])
        raised = False
    except TimeoutError:
        raised = True
    elapsed = _t.time() - started
    assert raised
    assert elapsed < 10
