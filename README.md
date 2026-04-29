# ⚖️ JusEasy — Gestão de Processos Jurídicos

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram)
![License](https://img.shields.io/badge/Licença-MIT-green)

Sistema pessoal de gestão de processos jurídicos com **bot no Telegram**, **dashboard web** e **inteligência artificial** integrada. Desenvolvido para advogados brasileiros que desejam centralizar intimações, prazos e tarefas em um único lugar.

---

## ⚠️ Aviso de migração — AASP API → Gmail OAB-ES

> **A v1 do JusEasy usava a API da AASP** para puxar intimações. Essa API foi descontinuada / não está mais disponível para todos os associados. A versão atual (v2) **substituiu essa fonte por leitura direta do Gmail** usando IMAP, pegando emails do **Recorte Digital da OAB** (testado com OAB-ES, mas o parser é genérico para o template Webjur Brasil).

**Se você precisa do código antigo que usa AASP**, consulte a branch [`old-AASP`](https://github.com/helioneto144/JusEasy/tree/old-AASP). Ela está congelada e não recebe atualizações.

| | v1 (`old-AASP`) | v2 (atual `main`) |
|---|---|---|
| Fonte de intimações | API da AASP | Gmail IMAP (label "OAB-ES") |
| Pré-requisito | Associado AASP/SP com chave de API | Conta Gmail + 2FA + App Password |
| Frequência | Cron 3x/dia (8h, 12h, 16h) | Cron 3x/dia (4h, 7h, 10h — refinável) |
| Custo | Anuidade AASP | Zero |

Tudo o mais (banco, IA, Telegram, dashboard) continua igual.

---

## ✨ Funcionalidades

- **🔔 Captura automática de intimações via email** — JusEasy acessa seu Gmail via IMAP, lê emails da OAB com label "OAB-ES", parseia o HTML do Recorte Digital (Webjur Brasil) e cria intimações no banco
- **🤖 Resumo IA de intimações** — A IA (Groq) resume cada intimação nova e sugere ação
- **📅 Alertas de prazos** — Notifica prazos dos próximos 3 dias antes que vençam
- **📋 Resumo diário inteligente** — Envia resumo pela manhã somente se houver tarefas, intimações não lidas ou urgências
- **📁 Gestão de processos** — Cadastre, edite e arquive processos com número CNJ; auto-criação de processo quando uma intimação chega para um número novo
- **📝 Tarefas e prazos** — Crie tarefas com prioridade, tipo e data de vencimento
- **🧠 Consulta jurídica com IA** — Use o comando `/ia` para tirar dúvidas com contexto do processo
- **🌐 Dashboard web** — Interface moderna com Tailwind CSS, acessível via navegador, responsiva mobile

---

## 📋 Pré-requisitos

| Serviço | Obrigatório | Finalidade | Custo |
|---------|-------------|------------|-------|
| [Supabase](https://supabase.com) | ✅ | Banco de dados PostgreSQL | Gratuito |
| [Telegram @BotFather](https://t.me/BotFather) | ✅ | Criar o bot | Gratuito |
| Conta **Gmail com 2FA** | ✅ | Recebe os emails do Recorte Digital + App Password para IMAP | Gratuito |
| Cadastro no Recorte Digital da sua **OAB Estadual** | ✅ | Recebe as intimações por email | Anuidade OAB |
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
  status text default 'em_andamento',
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

-- Tabela de notas (anotações livres em processos)
create table notas (
  id uuid primary key default gen_random_uuid(),
  processo_id uuid references processos(id) on delete cascade,
  conteudo text not null,
  created_at timestamptz default now()
);

-- Tabela de emails recebidos (auditoria + buffer pra parser)
create table emails_recebidos (
  id uuid primary key default gen_random_uuid(),
  from_addr text,
  subject text,
  body_html text,
  body_text text,
  message_id text,
  imap_uid text,
  received_at_source text,
  processed boolean default false,
  parse_error text,
  intimacoes_count integer default 0,
  received_at timestamptz default now()
);
create unique index idx_emails_recebidos_message_id
    on emails_recebidos(message_id) where message_id <> '';
create index idx_emails_recebidos_processed
    on emails_recebidos(processed) where processed = false;
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

### Passo 4 — Configurar o Gmail (App Password) ⭐ NOVO

> Esse passo substitui a chave AASP da v1.

1. **Ativar 2FA** em https://myaccount.google.com/security (necessário para gerar App Password)
2. Acesse https://myaccount.google.com/apppasswords
3. App: `Mail` · Device: `Other` → digite `JusEasy`
4. Copie a senha de **16 caracteres** gerada (ex: `abcd efgh ijkl mnop`) — **remova os espaços** ao colar no `.env`

5. **Criar filtro Gmail** para aplicar a label `OAB-ES` aos emails do Recorte Digital:
   - Gmail → Settings (engrenagem) → **See all settings** → **Filters and Blocked Addresses** → **Create a new filter**
   - **From**: o remetente do Recorte Digital da sua OAB Estadual.
     Exemplo OAB-ES: `oabes@recortedigital.adv.br`
   - Clique em **Create filter**
   - ☑ **Apply the label**: criar nova label `OAB-ES`
   - ☑ **Also apply filter to matching conversations** (para pegar emails antigos também)
   - Salvar

> O parser foi testado com o Recorte Digital da OAB-ES (template Webjur Brasil). Outras OABs estaduais que usem o mesmo serviço (Webjur Brasil) devem funcionar sem mudanças. Se sua OAB usa template diferente, será necessário ajustar `app/services/email_parser.py`.

---

### Passo 5 — Obter chave da Groq (IA)

1. Acesse [console.groq.com](https://console.groq.com) e crie uma conta gratuita
2. Vá em **API Keys** e crie uma nova chave
3. Copie a chave → use como `GROQ_API_KEY` e `AI_API_KEY`

> A Groq oferece um plano gratuito generoso, mais que suficiente para uso pessoal.

---

### Passo 6 — Configurar o `.env`

Edite o arquivo `.env` com todas as credenciais obtidas:

```env
# Supabase
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_ANON_KEY=sua-anon-key
DATABASE_URL=postgresql://postgres.seu-projeto:senha@host:6543/postgres

# Gmail IMAP (substitui AASP)
GMAIL_USER=seu-email@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop
GMAIL_IMAP_HOST=imap.gmail.com
GMAIL_IMAP_LABEL=OAB-ES

# Feature flags
AASP_ENABLED=false        # mantenha false se não tem chave AASP
OAB_ES_ENABLED=true       # ativa o pipeline de processamento

# Telegram
TELEGRAM_BOT_TOKEN=1234567890:AAExxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789

# IA (Groq)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=llama-3.3-70b-versatile

AI_API_KEY=gsk_xxxxxxxxxxxxxxxx
AI_BASE_URL=https://api.groq.com/openai/v1
AI_MODEL=llama-3.3-70b-versatile

# Geral
TIMEZONE=America/Sao_Paulo
APP_URL=http://SEU-IP-OU-DOMINIO:8000
```

> **Sobre AASP**: se você ainda tem chave AASP e quer usar paralelo (improvável), preencha `AASP_API_KEY` e `AASP_ENABLED=true`. O hash de deduplicação garante que não duplica intimações entre as duas fontes.

---

### Passo 7 — Deploy com Docker

```bash
docker compose up -d --build
```

Acesse o dashboard em **http://localhost:8000** (ou o IP do seu servidor).

Para ver os logs:
```bash
docker logs oracle --tail 50 -f
```

---

### Passo 8 — Validar o pipeline de email

Endpoints administrativos para testar:

```bash
# 1. Testar conexão IMAP (sem ler emails)
curl http://localhost:8000/api/gmail-test
# Esperado: {"ok":true,"label_existe":true,...}

# 2. Disparar coleta manual (lê UNSEEN com label OAB-ES, processa, notifica Telegram)
curl -X POST http://localhost:8000/api/check-gmail
# Esperado: {"status":"checked","emails_novos":N}

# 3. Reprocessar emails já no banco (debug)
curl -X POST http://localhost:8000/api/admin/reprocess-emails

# 4. Buscar emails antigos por subject (admin)
curl -X POST "http://localhost:8000/api/admin/gmail-fetch-by-subject?subject=Public.%201."
```

Após receber pelo menos 1 email com `Public. 1.` (ou maior) no subject:
- Você recebe **notificação Telegram** com o trecho da intimação + botões interativos
- Você recebe **resumo IA** (Groq) em até 3 linhas
- A intimação aparece no dashboard `/intimacoes` e fica vinculada ao processo (auto-criado se for número CNJ novo)

---

## 📱 Comandos do Telegram

| Comando | Descrição |
|---------|-----------|
| `/start` | Menu principal com todos os comandos |
| `/status` | Resumo: processos, intimações não lidas, tarefas urgentes |
| `/stats` | Estatísticas detalhadas (ativos/arquivados, concluídas semana) |
| `/resumo` | Dispara o resumo diário manualmente |
| `/intimacoes` | Lista as últimas intimações não lidas |
| `/processos` | Lista os processos cadastrados |
| `/processo NUMERO` | Detalhes de um processo (ex: `/processo 1234567-00.2024.8.26.0100`) |
| `/tarefas` | Lista tarefas pendentes |
| `/prazos` | Tarefas agrupadas por urgência |
| `/hoje` | Tarefas com vencimento hoje |
| `/semana` | Tarefas para os próximos 7 dias |
| `/calendario` | Visão semanal: tarefas + intimações por dia |
| `/tarefa TITULO\|DATA\|TIPO\|PRIORIDADE` | Cria tarefa (ex: `/tarefa Contestação\|2025-05-10\|prazo\|urgente`) |
| `/nota NUMERO TEXTO` | Adiciona anotação a um processo |
| `/busca TERMO` | Busca em processos, intimações e tarefas |
| `/ia [NUMERO] PERGUNTA` | Consulta jurídica com IA (ex: `/ia 1234... Qual o prazo para recurso?`) |
| `/yaml NUMERO` | Exporta o processo em YAML para análise externa |

### Tipos de tarefa válidos
`prazo` · `audiencia` · `peticao` · `recurso`

### Prioridades válidas
`urgente` · `alta` · `media` · `baixa`

---

## 🌐 Dashboard Web

Interface responsiva (mobile + desktop) com sidebar colapsável:

- **Dashboard** — visão geral, contadores, mini-calendário semanal, próximos prazos
- **Processos** — lista com filtros, busca, status (em andamento, audiência marcada, recurso, etc)
- **Detalhes do Processo** — timeline cronológica de intimações + tarefas + notas, dropdown de status, edição inline
- **Intimações** — listagem com filtro lidas/não lidas, paginação
- **Tarefas** — Kanban por prioridade + tabela completa, conclusão e exclusão
- **Busca global** (Cmd+K na sidebar) — pesquisa em processos, intimações e tarefas

---

## ⚙️ Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `SUPABASE_URL` | ✅ | URL do projeto Supabase |
| `SUPABASE_ANON_KEY` | ✅ | Chave anon do Supabase |
| `DATABASE_URL` | ✅ | Connection string PostgreSQL |
| `GMAIL_USER` | ✅ | Email Gmail que recebe os emails da OAB |
| `GMAIL_APP_PASSWORD` | ✅ | App Password de 16 chars (sem espaços) |
| `GMAIL_IMAP_LABEL` | — | Label do filtro Gmail (padrão: `OAB-ES`) |
| `OAB_ES_ENABLED` | ✅ | `true` para ativar o pipeline de email |
| `AASP_ENABLED` | — | `true` se você ainda tem chave AASP (legado) |
| `AASP_API_KEY` | — | Chave AASP (só se `AASP_ENABLED=true`) |
| `TELEGRAM_BOT_TOKEN` | ✅ | Token do bot criado no @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | ID do chat que receberá as notificações |
| `GROQ_API_KEY` | ⭐ | Chave Groq para resumos de intimações |
| `AI_API_KEY` | ⭐ | Chave para o comando /ia (pode ser a mesma Groq) |
| `APP_URL` | — | URL pública da aplicação (padrão: `http://localhost:8000`) |
| `TIMEZONE` | — | Fuso horário (padrão: `America/Sao_Paulo`) |

Mais detalhes do setup IMAP em [`docs/oab-es-email.md`](docs/oab-es-email.md).

---

## 🏗️ Tecnologias

- **Backend:** FastAPI + Python 3.11
- **Banco de dados:** Supabase (PostgreSQL)
- **Bot Telegram:** python-telegram-bot v21
- **Agendamento:** APScheduler (CronTrigger 4h/7h/10h America/Sao_Paulo)
- **IMAP:** imap-tools (login via App Password)
- **Parser HTML:** BeautifulSoup4 (template Webjur Brasil OAB-ES)
- **IA:** Groq (llama-3.3-70b-versatile)
- **Frontend:** Tailwind CSS + HTMX + Alpine.js (responsivo)
- **Deploy:** Docker + Docker Compose

---

## 🌳 Estrutura de branches

- **`main`** — versão atual (Gmail IMAP / OAB-ES). Recebe novos commits.
- **`old-AASP`** — versão antiga que usa a API da AASP. Congelada, não recebe atualizações. Use se ainda tem acesso à API e prefere essa fonte.

---

## 📄 Licença

MIT — sinta-se livre para usar, modificar e distribuir.

---

> Desenvolvido por [Helio Menezes Neto](https://github.com/helioneto144)
