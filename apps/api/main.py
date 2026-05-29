from fastapi import FastAPI

from apps.api.routers.auth import router as auth_router
from apps.api.routers.comments import comment_router
from apps.api.routers.comments import revision_router as comments_revision_router
from apps.api.routers.policies import router as policies_router
from apps.api.routers.revisions import router as revisions_router


def create_app() -> FastAPI:
    app = FastAPI(title="Easy Regulations API")
    app.include_router(auth_router)
    app.include_router(policies_router)
    app.include_router(revisions_router)
    app.include_router(comments_revision_router)
    app.include_router(comment_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
