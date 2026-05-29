from fastapi import FastAPI

from apps.api.routers.auth import router as auth_router


def create_app() -> FastAPI:
    app = FastAPI(title="Easy Regulations API")
    app.include_router(auth_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
