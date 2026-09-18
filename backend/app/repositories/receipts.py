"""Consultas CU25 sobre tablas existentes; ninguna escritura."""
from sqlalchemy import select

from app.models.branch import Branch
from app.models.client import Client
from app.models.employee import Employee
from app.models.employee_branch import EmployeeBranch
from app.models.payment import Payment
from app.models.sale import Sale
from app.models.user import User
from app.repositories.client_purchases import ClientPurchasesRepository


class ReceiptsRepository(ClientPurchasesRepository):
    def staff_purchase(self, sale_id, user_id):
        return self.db.execute(
            select(Sale, Branch)
            .join(Branch, Branch.id_sucursal == Sale.id_sucursal)
            .join(EmployeeBranch, EmployeeBranch.id_sucursal == Branch.id_sucursal)
            .join(Employee, Employee.id_empleado == EmployeeBranch.id_empleado)
            .where(Sale.id_venta == sale_id, Employee.id_usuario == user_id,
                   EmployeeBranch.estado.is_(True), Branch.estado.is_(True))
        ).one_or_none()

    def receipt_client(self, client_id):
        if client_id is None:
            return None
        return self.db.execute(
            select(User.nombre, User.apellido)
            .join(Client, Client.id_usuario == User.id_usuario)
            .where(Client.id_cliente == client_id)
        ).mappings().one_or_none()

    def receipt_payments(self, sale_id):
        return self.db.execute(
            select(Payment.medio, Payment.estado, Payment.monto, Payment.moneda)
            .where(Payment.id_venta == sale_id,
                   Payment.estado.in_(['APROBADO', 'REEMBOLSADO']))
        ).mappings().all()
