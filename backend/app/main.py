from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.admin_branches import router as admin_branches_router
from app.routers.admin_employee_branches import router as admin_employee_branches_router
from app.routers.admin_categories import router as admin_categories_router
from app.routers.admin_sizes import router as admin_sizes_router
from app.routers.admin_colors import router as admin_colors_router
from app.routers.admin_cities import router as admin_cities_router
from app.routers.admin_users import router as admin_users_router
from app.routers.admin_seasons import router as admin_seasons_router
from app.routers.admin_collections import router as admin_collections_router
from app.routers.admin_suppliers import router as admin_suppliers_router
from app.routers.auth import router as auth_router


app = FastAPI(
    title="FashionStore API",
    version="1.0.0"
)


origins = [
    "http://localhost:4201",
    "http://127.0.0.1:4201",
    "https://fashionstore-frontend-r9b5.onrender.com",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(admin_suppliers_router)
app.include_router(admin_seasons_router)
app.include_router(admin_collections_router)
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(admin_cities_router)
app.include_router(admin_categories_router)
app.include_router(admin_sizes_router)
app.include_router(admin_colors_router)
app.include_router(admin_branches_router)
app.include_router(admin_employee_branches_router)


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
