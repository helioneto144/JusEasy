# Captura de intimacoes via email OAB-ES (Gmail IMAP)

## Visao geral

A AASP API esta sendo descontinuada. Intimacoes agora chegam por email no Gmail
(`heliomenezesneto@gmail.com`) via Recorte Digital da OAB-ES.

O JusEasy faz **IMAP polling** dessa caixa, lendo emails UNSEEN com label
especifica e salvando crus em `emails_recebidos` (Fase 1). Parsing e pipeline
completo virao depois (Fase 2/3).

```
heliomenezesneto@gmail.com  (filtro Gmail aplica label "OAB-ES")
   ↓ JusEasy abre IMAP a cada 1h (07h-12h America/Sao_Paulo)
   ↓ FETCH UNSEEN INBOX/OAB-ES
   ↓ INSERT em emails_recebidos (HTML + texto + headers)
   ↓ STORE \Seen (evita reprocessar)
```

## Setup

### 1. Ativar 2FA no Gmail (1x)

https://myaccount.google.com/security
→ "Verificacao em duas etapas" → ativar.

### 2. Gerar App Password

https://myaccount.google.com/apppasswords
→ App: "Mail", Device: "Other" → digite "JusEasy"
→ Gera senha de 16 caracteres (ex: `abcd efgh ijkl mnop`)
→ Copia **sem os espacos** (`abcdefghijklmnop`).

### 3. Configurar `.env` no servidor

```bash
ssh -i /home/helio/Oracle/ssh-key-2026-03-18.key ubuntu@100.121.165.10
cd ~/oracle
nano .env
```

Adicionar:
```
GMAIL_USER=heliomenezesneto@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop
GMAIL_IMAP_LABEL=OAB-ES
OAB_ES_ENABLED=true
AASP_ENABLED=true
```

Restart o container:
```bash
docker restart oracle
```

### 4. Filtro Gmail (1x)

Gmail → engrenagem → **See all settings** → **Filters and Blocked Addresses**
→ **Create a new filter**

- **From**: descobrir o remetente exato olhando um email da OAB-ES
  (provavelmente algo tipo `noreply@oabes.org.br`)
- Click **Create filter**
- Marcar:
  - ☑ **Apply the label**: criar nova label chamada `OAB-ES`
  - ☐ Skip Inbox (opcional, se quiser tirar da caixa de entrada)
- **Create filter**

### 5. Validar conexao

Endpoint de smoke test:
```bash
curl -s https://<seu-juseasy>/api/gmail-test | python3 -m json.tool
```

Esperado:
```json
{
  "ok": true,
  "user": "heliomenezesneto@gmail.com",
  "label_alvo": "OAB-ES",
  "label_existe": true,
  "folders_count": 12
}
```

Se `label_existe: false`, criar a label no Gmail (basta aplicar a um email).

### 6. Disparo manual de coleta (debug)

```bash
curl -s -X POST https://<seu-juseasy>/api/check-gmail
```

Esperado:
```json
{ "status": "checked", "emails_novos": 3 }
```

### 7. Verificar no banco

```sql
SELECT id, from_addr, subject, length(body_html) AS html_len, received_at
FROM emails_recebidos
ORDER BY received_at DESC LIMIT 5;
```

## Schedule

Default: cron `0 7-12 * * *` (07h, 08h, 09h, 10h, 11h, 12h America/Sao_Paulo).

Ajustar conforme observacao dos horarios reais que a OAB-ES envia. Editar em
`app/main.py` -> `CronTrigger(hour="7-12", minute="0", timezone=tz)`.

## Troubleshooting

| Sintoma | Causa provavel | Acao |
|---|---|---|
| `gmail_imap: falha de login` | App Password incorreta ou 2FA nao ativado | Regerar App Password |
| `label_existe: false` | Label nao criada ainda | Aplicar label "OAB-ES" a 1 email no Gmail |
| `emails_novos: 0` mesmo com email no inbox | Email ja esta marcado como lido (\Seen) | Marcar como nao-lido manualmente p/ testar |
| Job nao roda no horario | Container reiniciou recentemente / scheduler nao iniciou | `docker logs oracle \| grep "scheduler started"` |

## Schema da tabela `emails_recebidos`

```sql
CREATE TABLE emails_recebidos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_addr text,
    subject text,
    body_html text,
    body_text text,
    message_id text,                  -- header Message-Id (dedup)
    imap_uid text,                    -- UID IMAP do email
    received_at_source text,          -- header Date do email
    processed boolean DEFAULT false,
    parse_error text,
    intimacoes_count integer DEFAULT 0,
    received_at timestamptz DEFAULT now()
);

CREATE UNIQUE INDEX idx_emails_recebidos_message_id
    ON emails_recebidos(message_id) WHERE message_id <> '';

CREATE INDEX idx_emails_recebidos_processed
    ON emails_recebidos(processed) WHERE processed = false;
```
