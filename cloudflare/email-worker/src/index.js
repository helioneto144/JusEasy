/**
 * Cloudflare Email Worker — JusEasy
 *
 * Recebe emails encaminhados pelo Email Routing,
 * processa o MIME (text/html) e POSTa para o webhook do JusEasy.
 *
 * Vars necessárias (Cloudflare Dashboard → Settings → Variables):
 *   WEBHOOK_URL     — ex: https://api.juseasy.fass.legal/webhook/email
 *   WEBHOOK_SECRET  — token aleatório (>= 32 chars), igual ao WEBHOOK_SECRET no .env do JusEasy
 */
import PostalMime from 'postal-mime';

export default {
  async email(message, env, ctx) {
    if (!env.WEBHOOK_URL || !env.WEBHOOK_SECRET) {
      console.error('WEBHOOK_URL ou WEBHOOK_SECRET nao configurados');
      message.setReject('Configuration error');
      return;
    }

    let parsed;
    try {
      const parser = new PostalMime();
      parsed = await parser.parse(message.raw);
    } catch (e) {
      console.error('Erro ao parsear MIME:', e);
      message.setReject('Parse error');
      return;
    }

    const payload = {
      from: parsed.from?.address || '',
      from_name: parsed.from?.name || '',
      to: (parsed.to || []).map(t => t.address).join(','),
      subject: parsed.subject || '',
      text: parsed.text || '',
      html: parsed.html || '',
      date: parsed.date || new Date().toISOString(),
      message_id: parsed.messageId || ''
    };

    try {
      const res = await fetch(env.WEBHOOK_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Webhook-Secret': env.WEBHOOK_SECRET,
          'User-Agent': 'JusEasy-Cloudflare-Email-Worker/1.0'
        },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        console.error(`Webhook retornou ${res.status}: ${await res.text()}`);
        // Não rejeita o email — Cloudflare reentrega na próxima
      } else {
        console.log(`OK: from=${payload.from} subject=${payload.subject.slice(0, 80)}`);
      }
    } catch (e) {
      console.error('Erro ao chamar webhook:', e);
      // Não rejeita — failures de rede são comuns
    }
  }
};
