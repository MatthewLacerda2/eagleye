"""Business logic layer.

Logic that is neither a thin handler nor pure data access lives here. Services
orchestrate one or more repositories and may be called by handlers. They take an
``AsyncSession`` and never open their own session, so the test rollback works.

Eagleye's capture, change filter, prompt, analyzer and alert logic live here.
"""
