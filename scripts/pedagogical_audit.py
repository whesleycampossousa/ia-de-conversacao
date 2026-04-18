"""
Pedagogical audit — bateria de 30 testes automatizados.

Para cada teste:
 1. Cria um "aluno virtual" com perfil A1-A2 brasileiro tímido baseado no
    docs/user_persona.md.
 2. Escolhe cenário + nível + modo (rotacionando para cobrir variedade).
 3. Simula 12 turnos de conversa chamando /api/chat.
 4. Em cada turno, valida a resposta da IA contra os 10 critérios
    pedagógicos da Whesley (ver persona file).
 5. Registra violações.

No final, gera audit_report.html com:
 - Overview (% pass, % fail)
 - Agrupamento por tipo de erro
 - Detalhe de cada falha com transcrição do turno problemático

Uso:
    .venv/Scripts/python.exe scripts/pedagogical_audit.py

Requer servidor local rodando em http://127.0.0.1:4344.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("ERRO: requests nao instalado (pip install requests)")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(ROOT / ".env")
except ImportError:
    ROOT = Path(__file__).resolve().parent.parent

BASE_URL = os.environ.get("AUDIT_BASE_URL", "http://127.0.0.1:4344")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "whesleycampos@hotmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

NUM_TESTS = int(os.environ.get("AUDIT_NUM_TESTS", "30"))
TURNS_PER_TEST = int(os.environ.get("AUDIT_TURNS_PER_TEST", "12"))

SCENARIOS = [
    "coffee_shop", "restaurant", "bakery", "pizza_delivery", "supermarket",
    "pharmacy", "doctor", "bank", "hotel", "airport", "tech_support",
    "hair_salon", "clothing_store", "gym", "library", "cinema", "bus_stop",
    "train_station", "renting_car", "lost_found", "neighbor", "free_conversation",
    "park", "museum", "school", "post_office", "dental_clinic",
]
LEVELS = ["beginner", "intermediate", "advanced"]
MODES = ["learning", "simulator"]

# Falas de aluno pré-scriptadas por cenário. Intencionalmente misturam casos
# "comportados" (respostas relevantes) com casos "desafiadores" (aluno faz
# pergunta, muda de assunto, erra grammar, cola em PT quando trava) — para
# forçar cada critério pedagógico.
STUDENT_SCRIPT_BY_SCENARIO: dict[str, list[str]] = {
    "coffee_shop": [
        "Hi!", "I'd like a coffee, please.", "A large one, please.",
        "With milk, please.", "Do you have any pastries?",
        "Can I see the options?", "How much is that?", "I'll pay with card.",
        "For here, please.", "Thank you.", "Have a nice day!", "Bye!",
    ],
    "restaurant": [
        "Good evening!", "A table for two, please.", "Yes, by the window would be nice.",
        "Can I see the menu?", "What do you recommend?", "I'll have the pasta.",
        "My friend wants the chicken.", "Water for me, please.",
        "Do you have any desserts?", "The tiramisu, please.",
        "Can we have the bill?", "Thank you, it was delicious!",
    ],
    "bank": [
        "Hello!", "I want to deposit some money.", "500 reais, please.",
        "Here is my ID.", "Do you have a receipt?", "Can I also check my balance?",
        "Thank you.", "Actually, can I also withdraw 100?",
        "I will pay some bills with it.", "How long does a transfer take?",
        "That is helpful, thank you.", "Have a good day!",
    ],
    "hotel": [
        "Hi, I have a reservation.", "My name is Leslie Smith.",
        "I will stay for three nights.", "Do you have Wi-Fi?",
        "What's the password?", "Is breakfast included?",
        "What time does breakfast start?", "Can I get a room upstairs?",
        "Can I pay now?", "With card, please.", "Thank you!", "Bye!",
    ],
    "airport": [
        "Good morning.", "Here is my passport and ticket.",
        "I have one suitcase.", "Can I take this bag as carry-on?",
        "I'd like a window seat, please.", "Where is gate 12?",
        "When does boarding start?", "Thank you very much.",
        "Is there food near the gate?", "I also have a connecting flight.",
        "Thanks again!", "Have a good day!",
    ],
    "doctor": [
        "Good morning, doctor.", "I have a pain in my stomach.",
        "It started two days ago.", "It hurts after I eat.",
        "I feel very tired too.", "No, I have not taken anything yet.",
        "I don't take any medicine regularly.", "What should I do?",
        "Do I need exams?", "How much will that cost?",
        "Thank you, doctor.", "See you next week.",
    ],
    "pharmacy": [
        "Hello, I have a headache. What do you recommend?",
        "Do you have something for a cold too?",
        "Yes, I have a prescription.", "Here you go.",
        "How do I take this?", "Is it before or after meals?",
        "Can I drive after taking it?", "How much is it?",
        "Can I pay with card?", "Thank you so much!",
        "Do you close late?", "Have a good day!",
    ],
    "free_conversation": [
        "Hi!", "I like a lot of different movies. One is Prison Break. Have you watched it?",
        "I also like music.", "What about you?",
        "Do you enjoy reading?", "My favorite book is Harry Potter.",
        "Have you read it?", "I think weekends are the best.",
        "What do you do on Sundays?", "Nice! Me too.",
        "It was good to chat.", "Bye!",
    ],
}

# Fallback script para cenários sem script dedicado — segue um padrão genérico.
GENERIC_SCRIPT = [
    "Hi!", "I'd like some help, please.", "Can you tell me more about that?",
    "What do you recommend?", "How much is it?", "Do you have another option?",
    "Thank you very much.", "One more question: is it quick?",
    "That sounds good.", "I'll take it.", "Great, thank you!", "Have a nice day!",
]


@dataclass
class TurnResult:
    turn: int
    user_text: str
    ai_text: str
    ai_pt: str
    turn_correction: Optional[dict]
    must_retry: bool
    suggested_words: list
    latency_ms: int
    violations: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    test_id: int
    scenario: str
    level: str
    mode: str
    turns: list[TurnResult] = field(default_factory=list)
    total_violations: int = 0
    error: Optional[str] = None
    started_at: str = ""
    ended_at: str = ""


def login() -> str:
    if not ADMIN_PASSWORD:
        raise SystemExit("ADMIN_PASSWORD ausente no .env — abortando")
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    if r.status_code != 200:
        raise SystemExit(f"Login falhou: HTTP {r.status_code} — {r.text[:200]}")
    token = r.json().get("token")
    if not token:
        raise SystemExit("Login nao retornou token")
    return token


def check_pedagogical_rules(user_text: str, ai_text: str, ai_pt: str,
                             correction: Optional[dict], must_retry: bool,
                             suggested_words: list, latency_ms: int,
                             level: str, mode: str, scenario: str,
                             turn: int) -> list[str]:
    """Aplica os 10 critérios da Whesley a um único turno."""
    violations = []
    ai_en = str(ai_text or "")
    user = str(user_text or "").strip()

    # 1. IA ignorou pergunta do aluno?
    if "?" in user:
        # Heurística: resposta deve começar com afirmação (Yes/No/I/We/Sure/Actually/Of course)
        # ou conter claramente uma afirmação como primeira oração.
        first_sent = re.split(r"[.!?]", ai_en, maxsplit=1)[0].strip().lower()
        answer_starters = (
            "yes", "no", "sure", "of course", "absolutely", "i ", "we ",
            "actually", "that", "it ", "there ", "oh", "you ", "they ",
            "indeed", "certainly", "my ", "our ", "right",
        )
        if not first_sent.startswith(answer_starters):
            violations.append(
                f"IA IGNOROU a pergunta do aluno. Aluno: {user!r}. "
                f"Primeira oracao da IA nao parece resposta: {first_sent!r}"
            )

    # 2. Correção muda significado? (heurística leve)
    if correction and isinstance(correction, dict):
        wrong = str(correction.get("wrong") or "").lower()
        right = str(correction.get("right") or "").lower()
        if wrong and right and len(right.split()) >= 3:
            # Checa se palavras-chave do "wrong" apareceram no "right"
            wrong_keywords = [w for w in re.findall(r"\w+", wrong) if len(w) > 3]
            right_keywords = set(re.findall(r"\w+", right))
            if wrong_keywords:
                overlap = sum(1 for w in wrong_keywords if w in right_keywords)
                ratio = overlap / len(wrong_keywords)
                if ratio < 0.3:  # pouco overlap = provavelmente mudou significado
                    violations.append(
                        f"CORRECAO pode ter MUDADO o significado. wrong={wrong!r} "
                        f"right={right!r} (overlap de palavras: {int(ratio*100)}%)"
                    )

    # 3. Follow-up com opções concretas? (learning mode, perguntas abertas)
    if mode == "learning" and "?" in ai_en and "?" not in user:
        last_q = ai_en.rsplit("?", 1)[0]
        last_q = re.split(r"[.!]\s*", last_q)[-1].lower()
        open_generic = [
            "anything else", "what would you like", "what do you want",
            "can i help you", "what can i do",
        ]
        has_options = any(w in last_q for w in [" or ", ","])
        is_generic = any(phrase in last_q for phrase in open_generic)
        if is_generic and not has_options:
            violations.append(
                f"PERGUNTA GENERICA sem opcoes: {last_q!r} — beginner/timido trava"
            )

    # 4. Vocabulário adequado ao nível?
    if level == "beginner":
        # Palavras C1+ que aluno A1/A2 nao conhece
        hard_words = [
            "accommodation", "amenities", "reservation", "prescription",
            "certainly", "definitely", "itinerary", "premise", "inquire",
            "comprehensive", "simultaneously", "subsequently", "accordingly",
        ]
        lower_ai = ai_en.lower()
        hit = [w for w in hard_words if re.search(rf"\b{w}\b", lower_ai)]
        if hit:
            violations.append(
                f"VOCABULARIO ACIMA DE A1 em resposta beginner: {hit}"
            )

    # 5. Contexto respeitado? (cenário certo)
    if scenario and scenario not in ("free_conversation", "basic_structures"):
        # Detecta misturas grosseiras — ex: "coffee" num cenário de banco
        cross_contexts = {
            "coffee_shop": ["deposit", "withdraw", "passport", "boarding"],
            "restaurant": ["deposit", "withdraw", "passport", "boarding"],
            "bank": ["coffee", "tea", "latte", "menu", "pizza"],
            "hotel": ["coffee order", "deposit some money"],
            "airport": ["coffee shop menu", "deposit"],
            "doctor": ["coffee", "menu", "deposit"],
            "pharmacy": ["coffee", "deposit", "passport"],
        }
        wrong_context_words = cross_contexts.get(scenario, [])
        lower_ai = ai_en.lower()
        hit = [w for w in wrong_context_words if w in lower_ai]
        if hit:
            violations.append(
                f"CONTEXTO MISTURADO no cenario {scenario}: {hit}"
            )

    # 6. Latência aceitável (<4000ms)?
    if latency_ms > 4000:
        violations.append(f"LATENCIA ALTA: {latency_ms}ms (limite 4000ms)")

    # 7. Retry forçado em beginner por erro pequeno?
    if level == "beginner" and must_retry and suggested_words:
        # Se a fala tem menos de 15 palavras e correction está ausente/vago,
        # forçar retry é duro demais
        if len(user.split()) < 15 and not correction:
            violations.append(
                "RETRY FORCADO em beginner sem correcao clara — desmotiva"
            )

    # 8. IA entrevistadora unilateral? (só pergunta, sem conteúdo)
    if len(ai_en.strip()) < 30 and ai_en.strip().endswith("?"):
        violations.append(
            f"RESPOSTA-ENTREVISTA: IA respondeu so com pergunta curta ({ai_en!r})"
        )

    # 9. Tradução PT presente quando requerida?
    if ai_en and not ai_pt and mode == "learning" and level in ("beginner",):
        violations.append("TRADUCAO PT AUSENTE em learning/beginner")

    # 10. Presença de jargão técnico em inglês na UI-facing text? (ignoramos — chat é EN)
    # Critério pulado para chat; relevante apenas pra UI.

    return violations


def generate_html_report(results: list[TestResult]) -> str:
    """Gera HTML pronto pra abrir no browser."""
    total_tests = len(results)
    failed_tests = sum(1 for r in results if r.total_violations > 0 or r.error)
    passed_tests = total_tests - failed_tests
    total_violations = sum(r.total_violations for r in results)
    total_turns = sum(len(r.turns) for r in results)

    # Agrupamento por tipo de violação
    violation_groups: dict[str, int] = {}
    for r in results:
        for t in r.turns:
            for v in t.violations:
                # Extrai prefixo antes do primeiro ":" como categoria
                category = v.split(":", 1)[0].split("(")[0].strip().split()[0:3]
                cat_key = " ".join(category)
                violation_groups[cat_key] = violation_groups.get(cat_key, 0) + 1

    grouped_html = ""
    for cat, count in sorted(violation_groups.items(), key=lambda x: -x[1]):
        grouped_html += f'<li><strong>{cat}</strong> — {count} ocorr&ecirc;ncia{"s" if count != 1 else ""}</li>'

    # Cards por teste
    test_cards_html = ""
    for r in results:
        color = "#E76F51" if (r.total_violations > 0 or r.error) else "#7FB069"
        status = "❌" if (r.total_violations > 0 or r.error) else "✓"
        error_html = f'<div class="error-box">Erro: {r.error}</div>' if r.error else ""
        turns_html = ""
        for t in r.turns:
            v_html = ""
            if t.violations:
                v_html = '<div class="violations">' + "".join(
                    f'<div class="violation">⚠ {v}</div>' for v in t.violations
                ) + '</div>'
            correction_html = ""
            if t.turn_correction:
                w = t.turn_correction.get("wrong", "")
                rg = t.turn_correction.get("right", "")
                correction_html = (
                    f'<div class="correction"><em>correction:</em> wrong="{w}" → right="{rg}"</div>'
                )
            turns_html += f"""
            <div class="turn {'has-violations' if t.violations else ''}">
                <div class="turn-head">Turno {t.turn} · {t.latency_ms}ms</div>
                <div class="user"><strong>👤</strong> {t.user_text}</div>
                <div class="ai"><strong>🤖</strong> {t.ai_text}</div>
                {correction_html}
                {v_html}
            </div>"""
        test_cards_html += f"""
        <details class="test-card" {'open' if r.total_violations > 0 else ''}>
            <summary style="border-left:4px solid {color};">
                {status} Teste #{r.test_id:02d} —
                <strong>{r.scenario}</strong> · {r.level} · {r.mode} ·
                {r.total_violations} viola&ccedil;&otilde;es
            </summary>
            {error_html}
            <div class="turns">{turns_html}</div>
        </details>"""

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Auditoria Pedag&oacute;gica — v2.0</title>
<style>
  body {{ font-family: 'Inter', system-ui, sans-serif; background:#1A2330; color:#F5F7FA; margin:0; padding:30px; line-height:1.5; }}
  h1 {{ font-family: 'Plus Jakarta Sans', sans-serif; color:#7FB069; margin-top:0; }}
  .overview {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:16px; margin-bottom:30px; }}
  .stat {{ background:#243140; border:1px solid rgba(127,176,105,0.3); border-radius:12px; padding:18px; }}
  .stat .n {{ font-size:2.2rem; font-weight:800; color:#7FB069; font-family:'Plus Jakarta Sans', sans-serif; }}
  .stat .l {{ color:#A8B5C0; font-size:0.85rem; }}
  .section {{ background:#243140; border-radius:14px; padding:20px; margin-bottom:20px; }}
  .section h2 {{ font-family:'Plus Jakarta Sans', sans-serif; color:#F5F7FA; margin-top:0; }}
  .section ul {{ color:#D0DCE5; }}
  details.test-card {{ background:#243140; border-radius:12px; margin-bottom:12px; padding:14px 18px; }}
  details.test-card summary {{ cursor:pointer; padding:8px 14px; user-select:none; font-size:0.95rem; }}
  details.test-card[open] summary {{ margin-bottom:12px; }}
  .turns {{ padding:0 0 0 16px; border-left:2px solid rgba(127,176,105,0.15); }}
  .turn {{ background:#1A2330; border-radius:10px; padding:12px; margin-bottom:10px; border:1px solid transparent; }}
  .turn.has-violations {{ border-color:rgba(231,111,81,0.4); }}
  .turn-head {{ font-size:0.75rem; color:#A8B5C0; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }}
  .user {{ color:#F5F7FA; padding:6px 0; }}
  .ai {{ color:#B8DAA7; padding:6px 0; }}
  .correction {{ background:rgba(231,111,81,0.08); padding:6px 10px; border-radius:6px; margin-top:6px; font-size:0.82rem; color:#F5C7B8; }}
  .violations {{ margin-top:8px; }}
  .violation {{ background:rgba(231,111,81,0.14); border:1px solid rgba(231,111,81,0.35); border-radius:8px; padding:8px 12px; margin-top:6px; color:#FFD5C9; font-size:0.85rem; }}
  .error-box {{ background:rgba(220,50,50,0.2); padding:12px; border-radius:8px; margin-bottom:10px; color:#FFB8B8; }}
  .meta {{ color:#A8B5C0; font-size:0.85rem; margin-bottom:20px; }}
</style>
</head>
<body>
<h1>🔍 Auditoria Pedag&oacute;gica — IA de Conversa&ccedil;&atilde;o v2.0</h1>
<div class="meta">Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ·
Persona: Whesley (public owner) · Base URL: {BASE_URL}</div>

<div class="overview">
  <div class="stat"><div class="n">{total_tests}</div><div class="l">testes executados</div></div>
  <div class="stat"><div class="n">{total_turns}</div><div class="l">turnos totais</div></div>
  <div class="stat"><div class="n" style="color:#7FB069">{passed_tests}</div><div class="l">testes sem viola&ccedil;&otilde;es</div></div>
  <div class="stat"><div class="n" style="color:#E76F51">{failed_tests}</div><div class="l">testes com viola&ccedil;&otilde;es</div></div>
  <div class="stat"><div class="n" style="color:#E76F51">{total_violations}</div><div class="l">viola&ccedil;&otilde;es detectadas</div></div>
</div>

<div class="section">
  <h2>📊 Viola&ccedil;&otilde;es por categoria</h2>
  <ul>{grouped_html or '<li>Nenhuma viola&ccedil;&atilde;o detectada 🎉</li>'}</ul>
</div>

<div class="section">
  <h2>🧪 Detalhe dos testes</h2>
  <p style="color:#A8B5C0; font-size:0.85rem;">Clique em cada teste para ver a transcri&ccedil;&atilde;o completa e viola&ccedil;&otilde;es por turno. Testes com viola&ccedil;&atilde;o j&aacute; vêm abertos.</p>
  {test_cards_html}
</div>
</body>
</html>"""
    return html


def run_single_test(token: str, test_id: int, scenario: str, level: str,
                    mode: str) -> TestResult:
    result = TestResult(
        test_id=test_id, scenario=scenario, level=level, mode=mode,
        started_at=datetime.now().isoformat(timespec="seconds"),
    )
    script = STUDENT_SCRIPT_BY_SCENARIO.get(scenario, GENERIC_SCRIPT)[:TURNS_PER_TEST]
    for i, user_text in enumerate(script, start=1):
        payload = {
            "text": user_text,
            "context": scenario,
            "practice_mode": mode,
            "difficulty": level,
            "turnCount": i,
            "lessonLang": "en",
        }
        t0 = time.time()
        try:
            r = requests.post(
                f"{BASE_URL}/api/chat",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
        except Exception as e:
            result.error = f"request failed on turn {i}: {e}"
            break
        latency_ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            result.error = f"HTTP {r.status_code} on turn {i}: {r.text[:200]}"
            break
        data = r.json()
        ai_en = str(data.get("text") or data.get("en") or "")
        ai_pt = str(data.get("translation") or data.get("pt") or "")
        correction = data.get("turn_correction")
        must_retry = bool(data.get("must_retry"))
        sw = data.get("suggested_words") or []

        violations = check_pedagogical_rules(
            user_text, ai_en, ai_pt, correction, must_retry, sw,
            latency_ms, level, mode, scenario, i,
        )
        result.turns.append(TurnResult(
            turn=i, user_text=user_text, ai_text=ai_en, ai_pt=ai_pt,
            turn_correction=correction if isinstance(correction, dict) else None,
            must_retry=must_retry, suggested_words=sw,
            latency_ms=latency_ms, violations=violations,
        ))
        result.total_violations += len(violations)

    result.ended_at = datetime.now().isoformat(timespec="seconds")
    return result


def main():
    print(f"Iniciando auditoria — {NUM_TESTS} testes × {TURNS_PER_TEST} turnos = "
          f"{NUM_TESTS * TURNS_PER_TEST} chamadas /api/chat")
    print(f"Alvo: {BASE_URL}")
    print("Login...")
    token = login()
    print(f"OK — token len={len(token)}")
    print("Aguardando 1s para evitar rate limit...")
    time.sleep(1)

    # Monta combinações variadas
    random.seed(42)
    combos = []
    for i in range(NUM_TESTS):
        scenario = SCENARIOS[i % len(SCENARIOS)]
        level = LEVELS[i % len(LEVELS)]
        mode = MODES[i % len(MODES)]
        combos.append((i + 1, scenario, level, mode))

    results: list[TestResult] = []
    t_start = time.time()
    for test_id, scenario, level, mode in combos:
        # ASCII-only console output (Windows cp1252 nao aceita ✓/❌)
        print(f"[{test_id:02d}/{NUM_TESTS}] {scenario} / {level} / {mode}...", end="", flush=True)
        res = run_single_test(token, test_id, scenario, level, mode)
        flag = "FAIL" if res.total_violations > 0 or res.error else "PASS"
        print(f" [{flag}] {len(res.turns)} turnos, {res.total_violations} violacoes")
        results.append(res)
        # Pequena pausa entre testes
        time.sleep(0.4)
    elapsed = time.time() - t_start
    print(f"\nConcluido em {elapsed:.1f}s")

    # Gera relatorio
    out = ROOT / "audit_report.html"
    html = generate_html_report(results)
    out.write_text(html, encoding="utf-8")
    print(f"Relatorio: {out}")

    # Tambem salva JSON raw
    json_out = ROOT / "audit_report.json"
    json_out.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"JSON cru: {json_out}")

    # Abre no browser
    try:
        import webbrowser
        webbrowser.open(out.as_uri())
    except Exception:
        pass


if __name__ == "__main__":
    main()
