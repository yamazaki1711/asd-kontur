"""Pinned logical profiles sharing one physical local Qwen runtime.

The construction consultant and domain harness deliberately have separate
prompts, tools, schemas, acceptance and readiness.  This module describes the
consultant only; existing Harness profiles remain owned by ``asd_kontur.harness``.
"""

CONSTRUCTION_CONSULTANT_PROFILE = "construction-consultant@2.1.0"
CONSTRUCTION_CONSULTANT_MODEL_PROFILE = "qwen3.8-27b-construction-consultant@1.0.0"
CONSTRUCTION_CONSULTANT_PLANNING_PROFILE = "construction-consultant-plan@2.9.0-temp0.1"
CONSTRUCTION_CONSULTANT_SYNTHESIS_PROFILE = "construction-consultant-synthesis@2.9.0-temp0.2"
CONSTRUCTION_CONSULTANT_VALIDATION_PROFILE = "construction-consultant-quality@2.9.0-temp0.0"
QWEN_DEVELOPER_WORKER_PROFILE = "qwen3.8-27b-developer-worker@1.0.0"
