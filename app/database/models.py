from sqlalchemy import Column, String, Text, Boolean, Integer, Numeric, Date, Time, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base
import uuid

Base = declarative_base()


class Processo(Base):
    __tablename__ = "processos"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    numero = Column(String(50), unique=True, nullable=False, index=True)
    vara = Column(String(100))
    comarca = Column(String(100))
    assunto = Column(Text)
    sintese = Column(Text)
    partes = Column(JSONB, default={"autor": [], "reu": []})
    valor_causa = Column(Numeric(15, 2))
    data_distribuicao = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Intimacao(Base):
    __tablename__ = "intimacoes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processo_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    data_disponibilizacao = Column(Date, nullable=False, index=True)
    data_publicacao = Column(Date)
    diario_oficial = Column(String(100))
    caderno = Column(String(50))
    pagina = Column(Integer)
    conteudo = Column(Text, nullable=False)
    numero_intimacao = Column(String(50))
    hash_conteudo = Column(String(64), unique=True)
    lida = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Tarefa(Base):
    __tablename__ = "tarefas"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processo_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    titulo = Column(String(200), nullable=False)
    descricao = Column(Text)
    data_vencimento = Column(Date, nullable=False, index=True)
    hora_vencimento = Column(Time)
    concluida = Column(Boolean, default=False)
    prioridade = Column(String(10), default="media")
    tipo = Column(String(50))
    notificado = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Configuracao(Base):
    __tablename__ = "configuracoes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chave = Column(String(100), unique=True, nullable=False)
    valor = Column(Text, nullable=False)
    descricao = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
