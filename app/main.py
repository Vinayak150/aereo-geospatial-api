"""API factory keeps tests isolated and avoids database creation on import."""

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pyproj import network
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from app.config import Settings
from app.db import Feature, UploadedFile, connect
from app.errors import APIError
from app.middleware import BodyLimitMiddleware
from app.schemas import ErrorResponse, FileInfo, Measurements
from app.services.files import process_upload

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        network.set_network_enabled(False)
        engine, factory = connect(config)
        application.state.session_factory = factory
        application.state.engine = engine
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="Geospatial File Measurement API",
        version="1.0.0",
        lifespan=lifespan,
        description=(
            "Upload KML 2.2 or one zipped Shapefile. Measurements use local UTM in "
            "metres and square metres. Results include per-feature measurement status."
        ),
    )
    application.add_middleware(BodyLimitMiddleware, max_bytes=config.max_upload_bytes + 64 * 1024)

    @application.exception_handler(APIError)
    async def domain_error(_: Request, error: APIError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        # Do not echo bodies, paths, uploaded bytes, or raw validation context.
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Check the file field, UUID path, and pagination parameters.",
                }
            },
            status_code=422,
        )

    @application.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "HTTP_ERROR", "message": "Request could not be processed."}},
            status_code=error.status_code,
            headers=error.headers,
        )

    @application.exception_handler(Exception)
    async def unexpected_error(_: Request, error: Exception) -> JSONResponse:
        logger.exception("Unexpected request failure", exc_info=error)
        return JSONResponse(
            {"error": {"code": "INTERNAL_ERROR", "message": "Processing failed unexpectedly."}},
            status_code=500,
        )

    def session(request: Request) -> Iterator[Session]:
        with request.app.state.session_factory() as connection:
            yield connection

    def find_file(identifier: UUID, connection: Session) -> UploadedFile:
        record = connection.get(UploadedFile, str(identifier))
        if record is None:
            raise APIError("FILE_NOT_FOUND", "No uploaded file has this ID.", 404)
        return record

    errors: dict[int | str, dict[str, Any]] = {
        code: {"model": ErrorResponse} for code in (400, 404, 413, 415, 422, 500)
    }

    @application.get("/health", tags=["Operations"])
    def health(connection: Annotated[Session, Depends(session)]) -> dict[str, str]:
        connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    @application.post(
        "/api/files/", response_model=FileInfo, status_code=201, responses=errors, tags=["Files"]
    )
    async def upload(
        request: Request,
        file: Annotated[UploadFile, File(description="KML or zipped Shapefile")],
        connection: Annotated[Session, Depends(session)],
    ) -> UploadedFile:
        form = await request.form()
        if len(form.multi_items()) != 1:
            raise APIError(
                "INVALID_REQUEST", "Provide exactly one multipart file field named file."
            )
        try:
            content = await file.read(config.max_upload_bytes + 1)
            return await run_in_threadpool(
                process_upload, content, file.filename, connection, config
            )
        finally:
            await file.close()

    @application.get("/api/files/{id}/", response_model=FileInfo, responses=errors, tags=["Files"])
    def file_information(
        id: UUID, connection: Annotated[Session, Depends(session)]
    ) -> UploadedFile:
        return find_file(id, connection)

    @application.get(
        "/api/files/{id}/measurements/",
        response_model=Measurements,
        responses=errors,
        tags=["Files"],
    )
    def measurements(
        id: UUID,
        connection: Annotated[Session, Depends(session)],
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict:
        record = find_file(id, connection)
        rows = connection.scalars(
            select(Feature)
            .where(Feature.file_id == str(id))
            .order_by(Feature.index)
            .offset(offset)
            .limit(limit)
        ).all()
        return {
            "file_id": id,
            "total": record.feature_count,
            "offset": offset,
            "limit": limit,
            "features": [row.result for row in rows],
        }

    return application
