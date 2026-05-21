"""CRUD /v1/hotword-groups."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from shared.repositories.hotword_repository import (
    DuplicateNameError,
    GroupNotFoundError,
    HotwordGroup,
    create_group,
    delete_group,
    get_group,
    list_groups,
    update_group,
)

router = APIRouter()


class CreateReq(BaseModel):
    name: str
    words: list[str]


class UpdateReq(BaseModel):
    name: str | None = None
    words: list[str] | None = None


def _serialize(g: HotwordGroup) -> dict:
    return {
        "id": g.id, "name": g.name, "words": g.words,
        "created_at": g.created_at, "updated_at": g.updated_at,
    }


@router.get("/hotword-groups")
async def list_route(request: Request):
    conn = request.app.state.db
    return [_serialize(g) for g in list_groups(conn)]


@router.post("/hotword-groups", status_code=201)
async def create_route(req: CreateReq, request: Request):
    conn = request.app.state.db
    try:
        gid = create_group(conn, name=req.name, words=req.words)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except DuplicateNameError:
        raise HTTPException(409, f"name '{req.name}' already exists") from None
    g = get_group(conn, gid)
    return _serialize(g)


@router.put("/hotword-groups/{group_id}")
async def update_route(group_id: int, req: UpdateReq, request: Request):
    conn = request.app.state.db
    try:
        update_group(conn, group_id, name=req.name, words=req.words)
    except GroupNotFoundError:
        raise HTTPException(404, f"group {group_id} not found") from None
    except DuplicateNameError:
        raise HTTPException(409, "name conflict") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    g = get_group(conn, group_id)
    return _serialize(g)


@router.delete("/hotword-groups/{group_id}", status_code=204)
async def delete_route(group_id: int, request: Request):
    conn = request.app.state.db
    try:
        delete_group(conn, group_id)
    except GroupNotFoundError:
        raise HTTPException(404, f"group {group_id} not found") from None
