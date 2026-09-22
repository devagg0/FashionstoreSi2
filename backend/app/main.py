from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.admin_branches import router as admin_branches_router
from app.routers.admin_sales_report import router as admin_sales_report_router
from app.routers.admin_inventory_report import router as admin_inventory_report_router
from app.routers.admin_reservations_report import router as admin_reservations_report_router
from app.routers.admin_inventory import router as admin_inventory_router
from app.routers.admin_global_inventory import router as admin_global_inventory_router
from app.routers.admin_inventory_movements import router as admin_inventory_movements_router
from app.routers.admin_employee_branches import router as admin_employee_branches_router
from app.routers.admin_categories import router as admin_categories_router
from app.routers.admin_sizes import router as admin_sizes_router
from app.routers.admin_colors import router as admin_colors_router
from app.routers.admin_cities import router as admin_cities_router
from app.routers.admin_users import router as admin_users_router
from app.routers.admin_seasons import router as admin_seasons_router
from app.routers.admin_collections import router as admin_collections_router
from app.routers.admin_suppliers import router as admin_suppliers_router
from app.routers.admin_products import router as admin_products_router
from app.routers.admin_promotions import router as admin_promotions_router
from app.routers.catalog import router as catalog_router
from app.routers.catalog_availability import router as catalog_availability_router
from app.routers.client_reservations import router as client_reservations_router
from app.routers.client_cart import router as client_cart_router
from app.routers.client_checkout import router as client_checkout_router
from app.routers.client_purchases import router as client_purchases_router
from app.routers.client_recommendations import router as client_recommendations_router
from app.routers.client_chatbot import router as client_chatbot_router
from app.routers.staff_reservations import router as staff_reservations_router
from app.routers.staff_sales import router as staff_sales_router
from app.routers.payments import router as payments_router
from app.routers.auth import router as auth_router
from app.routers.returns import router as returns_router
from app.routers.receipts import router as receipts_router


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
app.include_router(admin_products_router)
app.include_router(admin_promotions_router)
app.include_router(catalog_router)
app.include_router(catalog_availability_router)
app.include_router(client_reservations_router)
app.include_router(client_cart_router)
app.include_router(client_checkout_router)
app.include_router(client_purchases_router)
app.include_router(client_recommendations_router)
app.include_router(client_chatbot_router)
app.include_router(staff_reservations_router)
app.include_router(staff_sales_router)
app.include_router(payments_router)
app.include_router(returns_router)
app.include_router(receipts_router)
app.include_router(admin_seasons_router)
app.include_router(admin_collections_router)
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(admin_cities_router)
app.include_router(admin_categories_router)
app.include_router(admin_sizes_router)
app.include_router(admin_colors_router)
app.include_router(admin_branches_router)
app.include_router(admin_sales_report_router)
app.include_router(admin_inventory_report_router)
app.include_router(admin_reservations_report_router)
app.include_router(admin_inventory_router)
app.include_router(admin_global_inventory_router)
app.include_router(admin_inventory_movements_router)
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
