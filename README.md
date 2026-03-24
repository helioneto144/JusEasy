# ⚖️ JusEasy — Gestão de Processos Jurídicos

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram)
![License](https://img.shields.io/badge/Licença-MIT-green)

Sistema pessoal de gestão de processos jurídicos com **bot no Telegram**, **dashboard web** e **inteligência artificial** integrada. Desenvolvido para advogados brasileiros que desejam centralizar intimações (AASP), prazos e tarefas em um único lugar.

---

## ✨ Funcionalidades

- **🔔 Monitoramento automático de intimações** — Consulta a API da AASP (8h, 12h, 16h) e notifica no Telegram assim que uma nova intimação é detectada
- **🤖 Resumo IA de intimações** — Ao receber uma nova intimação, a IA (Groq) resume o conteúdo e informa qual ação tomar
- **📅 Alertas de prazos** — Notifica prazos dos próximos 3 dias antes que vençam
- **📋 Resumo diário inteligente** — Envia resumo pela manhã somente se houver tarefas, intimações não lidas ou urgências
- **📁 Gestão de processos** — Cadastre, edite e arquive processos com número CNJ
- **📝 Tarefas e prazos** — Crie tarefas com prioridade, tipo e data de vencimento
- **🧠 Consulta jurídica com IA** — Use o comando `/ia` para tirar dúvidas com contexto do processo
- **🌐 Dashboard web** — Interface moderna com Tailwind CSS, acessível via navegador

---

## 📋 Pré-requisitos

Antes de instalar, você precisará criar contas nos seguintes serviços:

| Serviço | Obrigatório | Finalidade | Custo |
|---------|-------------|------------|-------|
| [Supabase](https://supabase.com) | ✅ | Banco de dados PostgreSQL | Gratuito |
| [Telegram @BotFather](https://t.me/BotFather) | ✅ | Criar o bot | Gratuito |
| [AASP](https://www.aasp.org.br) | ✅ | Intimações do diário oficial | Associado AASP |
| [Groq](https://console.groq.com) | ⭐ Recomendado | IA para resumos e consultas | Gratuito |
| [Docker](https://docs.docker.com/get-docker/) | ✅ | Deploy da aplicação | Gratuito |

---

## 🚀 Instalação passo a passo

### Passo 1 — Clonar o repositório

```bash
git clone https://github.com/helioneto144/JusEasy.git
cd JusEasy
cp .env.example .env
```

---

### Passo 2 — Criar banco de dados no Supabase

1. Acesse [supabase.com](https://supabase.com) e crie um projeto
2. Vá em **SQL Editor** e execute o SQL abaixo para criar as tabelas:

```sql
-- Tabela de processos
create table processos (
  id uuid primary key default gen_random_uuid(),
  numero text unique not null,
  vara text,
  comarca text,
  assunto text,
  sintese text,
  partes jsonb default '{"autor": [], "reu": []}',
  valor_causa numeric(15,2),
  data_distribuicao date,
  arquivado boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Tabela de intimações
create table intimacoes (
  id uuid primary key default gen_random_uuid(),
  processo_id uuid,
  data_disponibilizacao date not null,
  data_publicacao date,
  diario_oficial text,
  caderno text,
  pagina integer,
  conteudo text not null,
  numero_intimacao text,
  hash_conteudo text unique,
  lida boolean default false,
  created_at timestamptz default now()
);

-- Tabela de tarefas
create table tarefas (
  id uuid primary key default gen_random_uuid(),
  processo_id uuid,
  titulo text not null,
  descricao text,
  data_vencimento date not null,
  hora_vencimento time,
  concluida boolean default false,
  prioridade text default 'media',
  tipo text,
  notificado boolean default false,
  created_at timestamptz default now()
);
```

3. Em **Project Settings > API**, copie:
   - **Project URL** → `SUPABASE_URL`
   - **anon public key** → `SUPABASE_ANON_KEY`

4. Em **Project Settings > Database**, copie a **Connection string (Transaction mode)** → `DATABASE_URL`

---

### Passo 3 — Criar o bot no Telegram

1. Abra o Telegram e converse com [@BotFather](https://t.me/BotFather)
2. Envie `/newbot` e siga as instruções
3. Copie o **token** gerado → `TELEGRAM_BOT_TOKEN`
4. Para obter seu **Chat ID**:
   - Envie qualquer mensagem para o seu bot
   - Acesse: `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
   - Procure por `"chat": {"id": NUMERO}` → esse número é o `TELEGRAM_CHAT_ID`

---

### Passo 4 — Obter chave da Groq (IA)

1. Acesse [console.groq.com](https://console.groq.com) e crie uma conta gratuita
2. Vá em **API Keys** e crie uma nova chave
3. Copie a chave → use como `GROQ_API_KEY` e `AI_API_KEY`

> A Groq oferece um plano gratuito generoso, mais que suficiente para uso pessoal.

---

### Passo 5 — Obter chave da AASP

1. Acesse o portal da [AASP](https://www.aasp.org.br) com sua conta de associado
2. Localize a seção de **Intimações Eletrônicas / API**
3. Gere ou copie sua chave de API → `AASP_API_KEY`

---

### Passo 6 — Configurar o `.env`

Edite o arquivo `.env` com todas as credenciais obtidas nos passos anteriores:

```env
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_ANON_KEY=sua-anon-key
DATABASE_URL=postgresql://postgres.seu-projeto:senha@host:6543/postgres

AASP_API_KEY=sua-chave-aasp
AASP_API_URL=https://intimacaoapi.aasp.org.br

TELEGRAM_BOT_TOKEN=1234567890:AAExxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789

GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=llama-3.3-70b-versatile

AI_API_KEY=gsk_xxxxxxxxxxxxxxxx
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile

POLLING_INTERVAL_HOURS=3
TIMEZONE=America/Sao_Paulo
APP_URL=http://SEU-IP-OU-DOMINIO:8000
```

---

### Passo 7 — Deploy com Docker

```bash
docker compose up -d --build
```

Acesse o dashboard em: **http://localhost:8000** (ou o IP do seu servidor)

Para ver os logs:
```bash
docker logs oracle --tail 50 -f
```

---

## 📱 Comandos do Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Menu principal com todos os comandos |
| `/status` | Resumo: processos, intimações não lidas, tarefas urgentes |
| `/resumo` | Dispara o resumo diário manualmente |
| `/intimacoes` | Lista as últimas intimações não lidas |
| `/processos` | Lista os processos cadastrados |
| `/processo NUMERO` | Detalhes de um processo específico (ex: `/processo 1234567-00.2024.8.26.0100`) |
| `/tarefas` | Lista tarefas pendentes |
| `/prazos` | Tarefas agrupadas por urgência |
| `/hoje` | Tarefas com vencimento hoje |
| `/semana` | Tarefas para os próximos 7 dias |
| `/tarefa TITULO\|DATA\|TIPO\|PRIORIDADE` | Cria uma tarefa (ex: `/tarefa Contestação\|2025-05-10\|prazo\|urgente`) |
| `/ia [NUMERO] PERGUNTA` | Consulta jurídica com IA (ex: `/ia 1234567-00.2024.8.26.0100 Qual o prazo para recurso?`) |
| `/yaml NUMERO` | Exporta o processo em YAML para análise |

### Tipos de tarefa válidos
`prazo` · `audiencia` · `peticao` · `recurso`

### Prioridades válidas
`urgente` · `alta` · `media` · `baixa`

---

## 🌐 Dashboard Web

Acesse `http://SEU-IP:8000` para usar a interface web:

- **Dashboard** — visão geral com contadores e últimas intimações
- **Processos** — lista, busca, criação e arquivamento de processos
- **Intimações** — listagem com filtro por lidas/não lidas
- **Tarefas** — lista com botão de conclusão e exclusão

---

## ⚙️ Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `SUPABASE_URL` | ✅ | URL do projeto Supabase |
| `SUPABASE_ANON_KEY` | ✅ | Chave anon do Supabase |
| `DATABASE_URL` | ✅ | Connection string PostgreSQL |
| `AASP_API_KEY` | ✅ | Chave da API de intimações AASP |
| `TELEGRAM_BOT_TOKEN` | ✅ | Token do bot criado no @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | ID do chat que receberá as notificações |
| `GROQ_API_KEY` | ⭐ | Chave Groq para resumos de intimações |
| `AI_API_KEY` | ⭐ | Chave para o comando /ia (pode ser a mesma Groq) |
| `APP_URL` | — | URL pública da aplicação (padrão: `http://localhost:8000`) |
| `TIMEZONE` | — | Fuso horário (padrão: `America/Sao_Paulo`) |
| `POLLING_INTERVAL_HOURS` | — | Intervalo de verificação em horas (padrão: `3`) |

---

## 🏗️ Tecnologias

- **Backend:** FastAPI + Python 3.11
- **Banco de dados:** Supabase (PostgreSQL)
- **Bot Telegram:** python-telegram-bot v21
- **Agendamento:** APScheduler
- **IA:** Groq (llama-3.3-70b-versatile)
- **Frontend:** Tailwind CSS + HTMX + Alpine.js
- **Deploy:** Docker + Docker Compose

---

## 📄 Licença

MIT — sinta-se livre para usar, modificar e distribuir.

---

> Desenvolvido por [Helio Menezes Neto](https://github.com/helioneto144)
