"""The catalogue of blocks a task's values and a leaderboard's columns are
built from, the one list the editor offers and the forge runs
(SIMPLER-CORE.md 10.1 and 14), with the leaves and facts a tree may read.
It holds nothing of any task, so it needs no session.
"""

from fastapi import APIRouter
from forge.api import blocks

from unicon.schemas.blocks import Block, Catalogue

router = APIRouter(tags=["blocks"])


@router.get("/blocks", operation_id="listBlocks", summary="The blocks a value or a column may use")
async def list_blocks() -> Catalogue:
    """Each block once, in the catalogue's order, with its forms and where
    each may be used."""
    return Catalogue(
        blocks=[Block.of(block) for block in blocks.CATALOGUE.values()],
        leaves=list(blocks.TASK_LEAVES),
        facts=list(blocks.TASK_FACTS),
        leaderboard_leaves=list(blocks.LEADERBOARD_LEAVES),
        leaderboard_facts=list(blocks.FACTS),
        skip=blocks.SKIP,
        languages=list(blocks.LANGUAGES),
    )
