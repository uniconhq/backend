"""The catalogue of blocks a task's values are built from, the one list the
editor offers and the forge runs (SIMPLER-CORE.md 14), with the leaves and
facts a tree may read. It holds nothing of any task, so it needs no
session.
"""

from fastapi import APIRouter
from forge.api import blocks

from unicon.schemas.blocks import Block, Catalogue

router = APIRouter(tags=["blocks"])


@router.get("/blocks", operation_id="listBlocks", summary="The blocks a value may use")
async def list_blocks() -> Catalogue:
    """Each block once, in the catalogue's order, with its forms."""
    return Catalogue(
        blocks=[Block.of(block) for block in blocks.CATALOGUE.values()],
        leaves=list(blocks.LEAVES),
        facts=list(blocks.TASK_FACTS),
        skip=blocks.SKIP,
    )
