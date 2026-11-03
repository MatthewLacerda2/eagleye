"""A site's loop keeps going after a round blows up."""

from worker import loops


async def test_site_loop_survives_exception(monkeypatch):
    calls = []

    async def exploding_round(deps, site_id, states):
        calls.append("round")
        raise RuntimeError("boom")

    async def keepalive(deps, site_id):
        calls.append("keepalive")
        return False

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(loops, "run_site_round", exploding_round)
    monkeypatch.setattr(loops, "run_keepalive", keepalive)
    await loops.site_loop(None, "site", 0.0, 120, sleep=no_sleep, max_iterations=3)
    assert calls.count("round") == 3
