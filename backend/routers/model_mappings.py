"""
Model Mapping Router — CRUD endpoints for managing model ID rewrite rules.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select, update

from database.connection import async_session
from models.model_mapping import ModelMapping

router = APIRouter()


class MappingCreateRequest(BaseModel):
    pattern: str
    target: str
    is_active: bool = True
    priority: int = 0


class MappingUpdateRequest(BaseModel):
    pattern: str | None = None
    target: str | None = None
    is_active: bool | None = None
    priority: int | None = None


class ReorderItem(BaseModel):
    id: str
    priority: int


class ReorderRequest(BaseModel):
    items: list[ReorderItem]


@router.get("/")
async def list_mappings():
    """List all mapping rules ordered by priority."""
    async with async_session() as session:
        result = await session.execute(
            select(ModelMapping).order_by(ModelMapping.priority, ModelMapping.created_at)
        )
        mappings = result.scalars().all()
        return {
            "items": [
                {
                    "id": m.id,
                    "pattern": m.pattern,
                    "target": m.target,
                    "is_active": m.is_active,
                    "priority": m.priority,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in mappings
            ],
            "total": len(mappings),
        }


@router.post("/")
async def create_mapping(req: MappingCreateRequest):
    """Create a new mapping rule."""
    mapping = ModelMapping(
        pattern=req.pattern,
        target=req.target,
        is_active=req.is_active,
        priority=req.priority,
    )
    async with async_session() as session:
        session.add(mapping)
        await session.commit()
        await session.refresh(mapping)
        return {
            "id": mapping.id,
            "pattern": mapping.pattern,
            "target": mapping.target,
            "is_active": mapping.is_active,
            "priority": mapping.priority,
            "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
        }


@router.patch("/{mapping_id}")
async def update_mapping(mapping_id: str, req: MappingUpdateRequest):
    """Update an existing mapping rule."""
    async with async_session() as session:
        result = await session.execute(
            select(ModelMapping).where(ModelMapping.id == mapping_id)
        )
        mapping = result.scalar_one_or_none()
        if not mapping:
            return {"success": False, "error": "Mapping not found"}
        if req.pattern is not None:
            mapping.pattern = req.pattern
        if req.target is not None:
            mapping.target = req.target
        if req.is_active is not None:
            mapping.is_active = req.is_active
        if req.priority is not None:
            mapping.priority = req.priority
        await session.commit()
        return {
            "success": True,
            "id": mapping.id,
            "pattern": mapping.pattern,
            "target": mapping.target,
            "is_active": mapping.is_active,
            "priority": mapping.priority,
        }


@router.delete("/{mapping_id}")
async def delete_mapping(mapping_id: str):
    """Delete a mapping rule."""
    async with async_session() as session:
        result = await session.execute(
            select(ModelMapping).where(ModelMapping.id == mapping_id)
        )
        mapping = result.scalar_one_or_none()
        if not mapping:
            return {"success": False, "error": "Mapping not found"}
        await session.delete(mapping)
        await session.commit()
        return {"success": True}


@router.put("/reorder")
async def reorder_mappings(req: ReorderRequest):
    """Batch update priorities for reordering."""
    async with async_session() as session:
        for item in req.items:
            await session.execute(
                update(ModelMapping)
                .where(ModelMapping.id == item.id)
                .values(priority=item.priority)
            )
        await session.commit()
        return {"success": True}
