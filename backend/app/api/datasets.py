from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from app.models.dataset import BuildDatasetRequest, DeployDatasetRequest, DeployDatasetResponse, JsonicDatasetRecord
from app.services.dataset.jsonic_builder import DatasetBuildError, JsonicDatasetBuilder
from app.services.dataset.registry import DatasetRegistry

router = APIRouter(prefix="/datasets/jsonic", tags=["datasets"])


def _builder(request: Request) -> JsonicDatasetBuilder:
    return request.app.state.jsonic_dataset_builder


def _registry(request: Request) -> DatasetRegistry:
    return request.app.state.dataset_registry


def _raise_dataset_error(error: DatasetBuildError) -> None:
    code_to_status = {
        "RAW_DATASET_BUILD_DISABLED": status.HTTP_403_FORBIDDEN,
        "RAW_LOGS_DISABLED": status.HTTP_403_FORBIDDEN,
        "SESSION_LIMIT_EXCEEDED": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "SESSIONS_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "DATASET_EMPTY": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "INVALID_ARTIFACT": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "ARTIFACT_NOT_FOUND": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    raise HTTPException(
        status_code=code_to_status.get(error.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": error.code, **error.payload},
    ) from error


@router.post("/build", response_model=JsonicDatasetRecord, status_code=status.HTTP_201_CREATED)
async def build_dataset(payload: BuildDatasetRequest, request: Request) -> JsonicDatasetRecord:
    try:
        return _builder(request).build(payload)
    except DatasetBuildError as error:
        _raise_dataset_error(error)


@router.get("/{dataset_id}", response_model=JsonicDatasetRecord)
async def get_dataset(dataset_id: str, request: Request) -> JsonicDatasetRecord:
    record = _registry(request).get(dataset_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DATASET_NOT_FOUND", "dataset_id": dataset_id},
        )
    return record


@router.get("/{dataset_id}/preview")
async def preview_dataset(
    dataset_id: str,
    request: Request,
    artifact: str = Query(default="events"),
    limit: int = Query(default=20, ge=1, le=500),
) -> dict:
    try:
        rows = _builder(request).preview(dataset_id=dataset_id, artifact=artifact, limit=limit)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DATASET_NOT_FOUND", "dataset_id": dataset_id},
        ) from exc
    except DatasetBuildError as error:
        _raise_dataset_error(error)

    return {"dataset_id": dataset_id, "artifact": artifact, "limit": limit, "rows": rows}


@router.get("/{dataset_id}/download")
async def download_dataset_artifact(
    dataset_id: str,
    request: Request,
    artifact: str = Query(default="manifest"),
) -> FileResponse:
    record = _registry(request).get(dataset_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DATASET_NOT_FOUND", "dataset_id": dataset_id},
        )
    if artifact not in {"events", "conversations", "manifest"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_ARTIFACT", "artifact": artifact},
        )

    path = record.artifact_path(artifact)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "ARTIFACT_NOT_FOUND", "artifact": artifact},
        )
    return FileResponse(path=path, filename=path.name)


@router.post("/{dataset_id}/deploy", response_model=DeployDatasetResponse)
async def deploy_dataset(
    dataset_id: str,
    payload: DeployDatasetRequest,
    request: Request,
) -> DeployDatasetResponse:
    try:
        return _builder(request).deploy(dataset_id=dataset_id, request=payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DATASET_NOT_FOUND", "dataset_id": dataset_id},
        ) from exc
    except DatasetBuildError as error:
        _raise_dataset_error(error)
