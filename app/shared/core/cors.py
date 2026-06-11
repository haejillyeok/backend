from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


DEFAULT_CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://haejillyeok.com",
    "https://agent.haejillyeok.com",
    "https://www.haejillyeok.com",
]


def add_cors_middleware(app: FastAPI) -> None:
    """허용된 프론트엔드 origin에서만 API를 호출할 수 있도록 CORS middleware를 등록합니다."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=DEFAULT_CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
