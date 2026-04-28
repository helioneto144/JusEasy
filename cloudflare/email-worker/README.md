# JusEasy — Email Worker (Cloudflare)

Worker que recebe emails encaminhados pelo Cloudflare Email Routing e POSTa para o webhook do JusEasy.

## Fluxo

```
OAB-ES → Gmail (filtro/forward) → intimacoes@<dominio> (Cloudflare) → Email Worker → POST → JusEasy
```

## Setup completo (Fase 1 — só conexão)

### 1. Pré-requisitos

- Domínio gerenciado pela Cloudflare (`fass.legal` ou `gmercandeli.com.br`)
- Cloudflare Tunnel rodando (já existe para `gmercandeli.com.br`)
- Conta Gmail com 2FA ativado

### 2. Cloudflare Tunnel — expor JusEasy publicamente

No servidor Oracle (já tem Cloudflare Tunnel rodando):

```bash
# Adicionar nova rota no config do tunnel (cloudflared)
sudo nano /etc/cloudflared/config.yml
```

Adicionar:
```yaml
ingress:
  - hostname: api.juseasy.fass.legal
    service: http://localhost:8000
  # ... outras rotas existentes
  - service: http_status:404
```

Criar registro DNS via dashboard ou:
```bash
cloudflared tunnel route dns <TUNNEL_ID> api.juseasy.fass.legal
sudo systemctl restart cloudflared
```

Validar:
```bash
curl https://api.juseasy.fass.legal/health
# → {"status":"healthy"}
```

### 3. Cloudflare Email Routing

Dashboard → seu domínio → **Email** → **Email Routing**:

1. Ativar Email Routing (cria os registros MX automaticamente)
2. Em **Custom addresses**: criar `intimacoes@fass.legal` (ou `intimacoes@<seu-dominio>`)
3. Em **Email Workers** → criar worker (próximo passo)
4. Vincular `intimacoes@<dominio>` → Worker

### 4. Deploy do Worker

```bash
cd /home/helio/Oracle/cloudflare/email-worker
npm install
npx wrangler login
npx wrangler deploy
```

Configurar secrets:
```bash
npx wrangler secret put WEBHOOK_URL
# Cole: https://api.juseasy.fass.legal/webhook/email

npx wrangler secret put WEBHOOK_SECRET
# Cole o mesmo token que vai no .env do servidor (use o gerado abaixo)
```

**Token sugerido (gerado para você)**:
```
74ad278cb2e312608cde78f02f5e6f97460b68b6bc88a8aabc460fd32022fb38
```

### 5. Atualizar .env do servidor JusEasy

No servidor:
```bash
ssh -i /home/helio/Oracle/ssh-key-2026-03-18.key ubuntu@100.121.165.10
cd ~/oracle
nano .env
```

Adicionar:
```
WEBHOOK_SECRET=74ad278cb2e312608cde78f02f5e6f97460b68b6bc88a8aabc460fd32022fb38
OAB_ES_ENABLED=false
AASP_ENABLED=true
```

Restart:
```bash
docker restart oracle
```

### 6. Filtro Gmail

Gmail → **Settings** → **Filters and Blocked Addresses** → **Create a new filter**:

- **From**: descobrir o remetente exato olhando um email já recebido (provavelmente `noreply@oabes.org.br` ou `recortedigital@oabes.org.br`)
- Click **Create filter**
- Marcar: ✅ **Forward it to**: `intimacoes@fass.legal`
- Marcar: ✅ **Apply label**: criar label "OAB-ES"
- Salvar

## Testes

### Teste 1: webhook responde 403 sem secret

```bash
curl -X POST https://api.juseasy.fass.legal/webhook/email -H "Content-Type: application/json" -d '{}'
# → 403 Unauthorized
```

### Teste 2: webhook responde 200 com secret correto

```bash
curl -X POST https://api.juseasy.fass.legal/webhook/email \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: 74ad278cb2e312608cde78f02f5e6f97460b68b6bc88a8aabc460fd32022fb38" \
  -d '{"from":"teste@example.com","subject":"Teste","html":"<p>oi</p>","text":"oi","date":"2026-04-28T10:00:00Z"}'
# → {"status":"received","id":"<uuid>"}
```

### Teste 3: end-to-end via email

Enviar email manualmente para `intimacoes@fass.legal` (de qualquer endereço) e verificar:
1. Logs do Worker no Cloudflare Dashboard → mostra "OK: from=..."
2. Logs do JusEasy: `docker logs oracle --tail 20` → "webhook/email: id=..."
3. Supabase: `SELECT id, from_addr, subject, length(body_html) FROM emails_recebidos ORDER BY received_at DESC LIMIT 5;`

### Teste 4: forward do Gmail

Enviar email para o Gmail do usuário simulando OAB-ES (assunto/remetente que casa com o filtro). Verificar que aparece no `emails_recebidos`.

## Próximos passos (Fase 2)

Quando 5+ emails reais da OAB-ES estiverem em `emails_recebidos`, criar o parser HTML em `app/services/email_parser.py`.

## Troubleshooting

**Worker não está sendo chamado**: verificar binding em Email Routing → Worker
**Webhook 403**: secrets diferentes entre Worker e .env do servidor
**Webhook 503**: WEBHOOK_SECRET vazio no .env do servidor — restart container após mudança
**Email não entrega**: verificar registros MX, esperar até 1h após mudança DNS
