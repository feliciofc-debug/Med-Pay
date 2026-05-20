"""Modelos SQLAlchemy do MedPag.

Importar TODOS os models aqui para que o Alembic os descubra automaticamente.
"""

from app.models.auditoria import Auditoria
from app.models.beneficiario import Beneficiario
from app.models.cliente import Cliente
from app.models.empresa_config import EmpresaConfig, TipoInscricao
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User, UserRole

__all__ = [
    "Auditoria",
    "Beneficiario",
    "Cliente",
    "EmpresaConfig",
    "Lote",
    "Pagamento",
    "StatusLote",
    "StatusPagamento",
    "TipoInscricao",
    "User",
    "UserRole",
]
