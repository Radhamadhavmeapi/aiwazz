"""Scheduled tasks (registered with scheduler.every)."""
from scheduler import every


@every("plan-sweep", 3600, first_delay=20)
async def plan_sweep(sessionmaker, app) -> str:
    from usage import expire_plans, purge_old_invite_requests
    async with sessionmaker() as db:
        n = await expire_plans(db)
        m = await purge_old_invite_requests(db)
    return f"{n} plan(s) ended, {m} old invite request(s) deleted"


@every("dunning", 3600, first_delay=60)
async def dunning(sessionmaker, app) -> str:
    from billing import dunning as d
    async with sessionmaker() as db:
        return await d.run(db)
