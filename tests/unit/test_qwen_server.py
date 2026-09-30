from __future__ import annotations

from asd_kontur.assistant.qwen_server import QwenRuntimeState


def test_qwen_runtime_state_distinguishes_loading_idle_and_generation() -> None:
    state = QwenRuntimeState()

    assert state.snapshot()["status"] == "QWEN_MODEL_LOADING"

    state.model_ready(object(), object(), object())
    assert state.snapshot()["status"] == "QWEN_READY_IDLE"
    assert state.runtime() is not None

    state.generation_started()
    generating = state.snapshot()
    assert generating["status"] == "QWEN_GENERATING"
    assert generating["generation_started_at"] is not None

    state.generation_finished()
    idle = state.snapshot()
    assert idle["status"] == "QWEN_READY_IDLE"
    assert idle["generation_started_at"] is None
    assert idle["completed_requests"] == 1


def test_qwen_runtime_state_exposes_fatal_loader_error_without_model() -> None:
    state = QwenRuntimeState()

    state.model_error(RuntimeError("model unavailable"))

    snapshot = state.snapshot()
    assert snapshot["status"] == "QWEN_ERROR"
    assert snapshot["last_error"] == "RuntimeError"
    assert state.runtime() is None
