"""Professional, workspace-scoped assistant application boundary.

The package initializer deliberately has no third-party imports so the isolated
MLX runtime can execute ``asd_kontur.assistant.qwen_server`` without carrying
the web application's PostgreSQL dependency set.
"""
