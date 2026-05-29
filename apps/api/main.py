from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Easy Regulations API")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
