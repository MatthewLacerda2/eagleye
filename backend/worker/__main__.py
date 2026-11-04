"""Entry point: ``python -m worker``."""

import asyncio

from worker.loops import main

if __name__ == "__main__":
    asyncio.run(main())
