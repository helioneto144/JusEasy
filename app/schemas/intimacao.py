from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from uuid import UUID


class IntimacaoBase(BaseModel):
    processo_id: Optional[UUID] = None
    data_disponibilizacao: date
    data_publicacao: Optional[date] = None
    diario_oficial: Optional[str] = None
    caderno: Optional[str] = None
    pagina: Optional[int] = None
    conteudo: str
    numero_intimacao: Optional[str] = None
    hash_conteudo: Optional[str] = None


class IntimacaoCreate(IntimacaoBase):
    pass


class IntimacaoResponse(IntimacaoBase):
    id: UUID
    lida: bool
    created_at: datetime

    class Config:
        from_attributes = True
