from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


class PartesSchema(BaseModel):
    autor: List[str] = []
    reu: List[str] = []


class ProcessoBase(BaseModel):
    numero: str
    vara: Optional[str] = None
    comarca: Optional[str] = None
    assunto: Optional[str] = None
    sintese: Optional[str] = None
    partes: Optional[PartesSchema] = None
    valor_causa: Optional[Decimal] = None
    data_distribuicao: Optional[date] = None


class ProcessoCreate(ProcessoBase):
    pass


class ProcessoUpdate(BaseModel):
    vara: Optional[str] = None
    comarca: Optional[str] = None
    assunto: Optional[str] = None
    sintese: Optional[str] = None
    partes: Optional[PartesSchema] = None
    valor_causa: Optional[Decimal] = None
    data_distribuicao: Optional[date] = None


class ProcessoResponse(ProcessoBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
