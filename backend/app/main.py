from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.admin_cities import router as admin_cities_router
from app.routers.admin_users import router as admin_users_router
from app.routers.auth import router as auth_router


app = FastAPI(
    title="FashionStore API",
    version="1.0.0"
)


origins = [
    "http://localhost:4201",
    "http://127.0.0.1:4201",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(admin_cities_router)


@app.get("/")
def root():
    return {
        "message": "FashionStore API funcionando"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }
