const assert = require('assert');
const fs = require('fs');
const path = require('path');
const http = require('http');
const { chromium } = require('playwright');

const DEFAULT_REMOTE_URL = 'https://ia-de-conversacao.vercel.app/practice.html?context=coffee_shop&title=Coffee%20Shop&lessonLang=en&structured=off&testHooks=1';
const APP_URL = process.env.UI_APP_URL || DEFAULT_REMOTE_URL;

function jsonResponse(route, payload, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(payload),
  });
}

function startStaticServer(rootDir, port = 9077) {
  const mimeByExt = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.ico': 'image/x-icon'
  };

  const server = http.createServer((req, res) => {
    try {
      const rawPath = decodeURIComponent((req.url || '/').split('?')[0]);
      const safePath = rawPath === '/' ? '/index.html' : rawPath;
      const fullPath = path.normalize(path.join(rootDir, safePath));
      if (!fullPath.startsWith(path.normalize(rootDir))) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
      }

      fs.readFile(fullPath, (err, data) => {
        if (err) {
          res.writeHead(404);
          res.end('Not found');
          return;
        }
        const ext = path.extname(fullPath).toLowerCase();
        res.writeHead(200, { 'Content-Type': mimeByExt[ext] || 'application/octet-stream' });
        res.end(data);
      });
    } catch (error) {
      res.writeHead(500);
      res.end('Server error');
    }
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

async function main() {
  const audioPath = path.resolve(__dirname, '..', 'test_audio.mp3');
  const audioBytes = fs.existsSync(audioPath) ? fs.readFileSync(audioPath) : Buffer.from('ID3');
  const failureShot = path.resolve(__dirname, '..', 'test_reports', 'ui_popup_flow_failure.png');
  const successShot = path.resolve(__dirname, '..', 'test_reports', 'ui_popup_flow_success.png');

  let staticServer = null;
  let appUrl = APP_URL;
  if (process.env.UI_LOCAL_SERVER === '1') {
    const rootDir = path.resolve(__dirname, '..');
    const port = Number(process.env.UI_LOCAL_SERVER_PORT || 9077);
    staticServer = await startStaticServer(rootDir, port);
    appUrl = `http://127.0.0.1:${port}/practice.html?context=coffee_shop&title=Coffee%20Shop&lessonLang=en&structured=off&testHooks=1`;
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();
  const errors = [];

  await context.addInitScript(() => {
    localStorage.setItem('practice_mode', 'learning');
    localStorage.setItem('practice_difficulty', 'intermediate');
    localStorage.setItem('confirm_transcription', 'false');
    localStorage.setItem('auto_translate', 'true');
    localStorage.setItem('onboarding_done', 'true');
    window.__ENABLE_UI_TEST_HOOKS__ = true;
  });

  await context.route('**/api/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const pathname = url.pathname;
    const method = req.method();

    if (pathname === '/api/conversations' && method === 'DELETE') {
      return jsonResponse(route, { ok: true });
    }
    if (pathname === '/api/usage/track' && method === 'POST') {
      return jsonResponse(route, { ok: true, remaining_seconds: 10800, is_blocked: false });
    }
    if (pathname === '/api/usage/status' && method === 'GET') {
      return jsonResponse(route, { remaining_seconds: 10800, is_blocked: false, weekend_limit_seconds: 10800, seconds_used: 0 });
    }
    if (pathname === '/api/chat' && method === 'POST') {
      const body = JSON.parse(req.postData() || '{}');
      return jsonResponse(route, {
        text: "Okay! You can also say: \"I'd like a hot coffee, please.\" What kind of coffee would you like?",
        translation: "Certo! Voce tambem pode dizer: \"Eu gostaria de um cafe quente, por favor.\" Que tipo de cafe voce gostaria?",
        must_retry: false,
        suggested_words: [],
        turn_feedback: {
          kind: 'ok',
          user_text: body.text || '',
          suggested_text: body.text || '',
          reason: 'Sua resposta esta correta para o contexto.'
        },
        learning_correction_kind_enabled: true
      });
    }
    if (pathname === '/api/suggestions' && method === 'POST') {
      // Intencionalmente ruim: o frontend deve filtrar e priorizar as corretas pelo contexto.
      return jsonResponse(route, {
        suggestions: [
          { en: 'Small, please.', pt: 'Pequeno, por favor.' },
          { en: 'I want a medium.', pt: 'Eu quero um medio.' },
          { en: 'Large is good, thank you.', pt: 'Grande esta bom, obrigado.' }
        ]
      });
    }
    if (pathname === '/api/tts' && method === 'POST') {
      return route.fulfill({
        status: 200,
        contentType: 'audio/mpeg',
        body: audioBytes
      });
    }

    return jsonResponse(route, { ok: true });
  });

  try {
    await page.goto(appUrl, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#start-btn', { state: 'visible', timeout: 15000 });
    await page.locator('#start-btn').click({ force: true });

    const tipsVisible = await page.locator('#tips-modal').isVisible().catch(() => false);
    if (tipsVisible) {
      await page.click('#tips-modal-ok');
    }

    await page.waitForFunction(() => {
      const overlay = document.getElementById('start-overlay');
      return overlay && overlay.style.display === 'none';
    }, { timeout: 15000 });

    await page.waitForFunction(() => {
      return !!window.__practiceTestHooks && typeof window.__practiceTestHooks.processUserResponse === 'function';
    }, { timeout: 15000 });

    await page.evaluate(() => {
      window.__uiTestPendingTurn = window.__practiceTestHooks.processUserResponse('A water hot coffee.');
      return true;
    });

    const popup = page.locator('.learning-feedback-overlay');
    await popup.waitFor({ state: 'visible', timeout: 20000 });
    const step1Text = await popup.innerText();

    if (!/Precisa ajustar|Forma sugerida|Ajuste/i.test(step1Text)) {
      errors.push('Step 1 do popup não marcou ajuste/correção.');
    }
    if (/Resposta correta/i.test(step1Text)) {
      errors.push('Step 1 do popup marcou resposta como correta indevidamente.');
    }
    if (!/I'd like a hot coffee, please\./i.test(step1Text)) {
      errors.push('Step 1 do popup não exibiu a sugestão esperada: "I\'d like a hot coffee, please."');
    }

    await page.locator('.learning-feedback-btn.primary', { hasText: /Proximo|Próximo/i }).click();
    await page.waitForTimeout(300);
    const step2Text = await popup.innerText();

    if (!/(I would like a hot coffee, please\.|Can I have a medium latte, please\?|Just a small black coffee, please\.)/i.test(step2Text)) {
      errors.push('Step 2 do popup não trouxe opções alinhadas à pergunta "What would you like today?".');
    }
    if (/(Small, please\.|I want a medium\.|Large is good, thank you\.)/i.test(step2Text)) {
      errors.push('Step 2 do popup ainda exibiu opções de tamanho (desalinhadas da pergunta inicial).');
    }

    await page.locator('.learning-feedback-btn.primary', { hasText: /Continuar/i }).click();
    await popup.waitFor({ state: 'hidden', timeout: 10000 });

    await page.evaluate(async () => {
      if (window.__uiTestPendingTurn && typeof window.__uiTestPendingTurn.then === 'function') {
        await window.__uiTestPendingTurn;
      }
    });

    await page.waitForTimeout(1500);
    const chatText = await page.locator('#chat-window').innerText();
    if (!/What kind of coffee would you like\?/i.test(chatText)) {
      errors.push('A pergunta seguinte da IA não apareceu no chat.');
    }

    const suggestionText = await page.locator('.suggested-words-card').innerText().catch(() => '');
    if (!/(A latte, please\.|A cappuccino, please\.|A small black coffee, please\.)/i.test(suggestionText)) {
      errors.push('As 3 sugestões na tela após o popup não alinharam com "What kind of coffee would you like?".');
    }

    if (errors.length) {
      fs.mkdirSync(path.dirname(failureShot), { recursive: true });
      await page.screenshot({ path: failureShot, fullPage: true });
      console.error('UI_POPUP_E2E_FAIL');
      errors.forEach((err, idx) => console.error(`${idx + 1}. ${err}`));
      process.exitCode = 1;
      return;
    }

    fs.mkdirSync(path.dirname(successShot), { recursive: true });
    await page.screenshot({ path: successShot, fullPage: true });
    console.log('UI_POPUP_E2E_PASS');
    console.log(`Screenshot: ${successShot}`);
  } finally {
    await browser.close();
    if (staticServer) {
      await new Promise((resolve) => staticServer.close(resolve));
    }
  }
}

main().catch((err) => {
  console.error('UI_POPUP_E2E_ERROR', err);
  process.exit(1);
});
