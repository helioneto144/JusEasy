from pydantic import BaseModel
from typing import Optional
from datetime import date, time, datetime
from uuid import UUID


class TarefaBase(BaseModel):
    processo_id: Optional[UUID] = None
    titulo: str
    descricao: Optional[str] = None
    data_vencimento: date
    hora_vencimento: Optional[time] = None
    prioridade: str = "media"
    tipo: Optional[str] = None


class TarefaCreate(TarefaBase):
    pass


class TarefaUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    data_vencimento: Optional[date] = None
    hora_vencimento: Optional[time] = None
    concluida: Optional[bool] = None
    prioridade: Optional[str] = None
    tipo: Optional[str] = None


class TarefaResponse(TarefaBase):
    id: UUID
    concluida: bool
    notificado: bool
    created_at: datetime

    class Config:
        from_attributes = True
