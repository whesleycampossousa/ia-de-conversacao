"""
Re-analisa audit_report.json aplicando detectores MAIS PRECISOS, sem precisar
rodar a bateria de 360 chamadas de novo. Grava um novo audit_report.html.

Melhorias no detector:
 - "IA ignorou pergunta" agora é muito mais conservador:
   - Só marca se a PRIMEIRA ORAÇÃO não contém nenhum sinal de resposta
   - Aceita muitos starters válidos (A/The/Our/Here/Let/Sure/For/At/...)
   - Pergunta específica como "How much?" → aceita qualquer número/"$" na resposta
   - Pergunta "When/What time?" → aceita hora/data
   - Pergunta "Where?" → aceita preposição de lugar
 - Corrige o falso positivo principal que estourou as estatísticas
"""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


ANSWER_STARTERS_EN = tuple(s.lower() for s in [
    "yes", "no", "sure", "of course", "absolutely", "certainly", "definitely",
    "i ", "i'll", "i'd", "i'm", "i've", "we ", "we'll", "we're",
    "actually", "indeed", "that ", "that's", "it ", "it's", "there ", "there's",
    "oh", "you ", "you're", "you'll", "they ", "they're",
    "my ", "our ", "your ", "his ", "her ", "their ",
    "right", "sounds", "great", "perfect", "good", "fine", "cool", "nice",
    "thanks", "thank",
    # Service / object starters typical for answering "what/how much/where/when":
    "a ", "an ", "the ", "one ", "two ", "three ", "four ", "five ",
    "here ", "here's", "let ", "let me", "let's",
    "for ", "at ", "in ", "on ", "around ", "near ", "by ",
    "since ", "until ", "before ", "after ", "from ",
    "about ", "approximately", "roughly", "usually", "typically",
    "sorry", "unfortunately",
    "hmm", "well",
])


def has_price_or_amount(text: str) -> bool:
    """Detecta menção a preço/quantidade (resposta pra 'how much?')."""
    if re.search(r"\$|€|£|R\$", text):
        return True
    if re.search(r"\b\d+\s*(dollars|reais|euros|bucks|cents)\b", text, re.IGNORECASE):
        return True
    if re.search(r"\b(free|no charge|on the house)\b", text, re.IGNORECASE):
        return True
    return False


def has_time_or_date(text: str) -> bool:
    if re.search(r"\b\d{1,2}[:\.]?\d{0,2}\s*(am|pm|a\.m\.|p\.m\.|o'clock)?\b", text, re.IGNORECASE):
        return True
    if re.search(r"\b(morning|afternoon|evening|night|tomorrow|today|tonight|yesterday|week|month|year|days?|hours?|minutes?)\b", text, re.IGNORECASE):
        return True
    if re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text, re.IGNORECASE):
        return True
    return False


def has_location(text: str) -> bool:
    loc_words = r"\b(here|there|next to|behind|in front|near|across|down|upstairs|downstairs|inside|outside|to your left|to your right|first floor|second floor|aisle|gate|terminal|section|counter|area|hall|room|lobby|entrance|exit)\b"
    return bool(re.search(loc_words, text, re.IGNORECASE))


def detect_ia_ignored_question(user_text: str, ai_text: str) -> bool:
    """Retorna True APENAS se houver forte evidência de que a IA não respondeu."""
    u = (user_text or "").strip()
    a = (ai_text or "").strip()
    if "?" not in u or not a:
        return False

    first_sent = re.split(r"(?<=[.!?])\s+", a, maxsplit=1)[0].strip()
    first_lower = first_sent.lower()

    # Already starts with a known answer starter → likely answered
    if any(first_lower.startswith(s) for s in ANSWER_STARTERS_EN):
        return False

    # Specific question types: check if response contains info relevant
    u_lower = u.lower()
    if "how much" in u_lower or "price" in u_lower or "cost" in u_lower:
        if has_price_or_amount(a):
            return False
    if "when" in u_lower or "what time" in u_lower or "how long" in u_lower:
        if has_time_or_date(a):
            return False
    if "where" in u_lower:
        if has_location(a):
            return False
    if "have you" in u_lower or "did you" in u_lower or "do you" in u_lower:
        # Personal question — needs a first-person or yes/no starter which is
        # already covered by ANSWER_STARTERS_EN. If reached here, likely ignored.
        return True
    if "can you" in u_lower or "could you" in u_lower or "would you" in u_lower:
        # request form — "Certainly / Of course" already in starters
        return True

    # Fall-through: only flag if the AI immediately starts with a fresh question
    if a.lstrip().endswith("?") and "?" not in first_sent:
        pass  # will be checked below
    # If first sentence IS itself a question → ignored
    if first_sent.endswith("?"):
        return True

    # Otherwise, assume answered (conservative default)
    return False


def detect_generic_followup(ai_text: str, user_text: str, mode: str) -> str | None:
    """Retorna descrição da violação ou None."""
    if mode != "learning":
        return None
    a = ai_text or ""
    if "?" not in a or (user_text and "?" in user_text):
        return None
    last_q = a.rsplit("?", 1)[0]
    last_q = re.split(r"[.!]\s*", last_q)[-1].strip().lower()
    generic = [
        "anything else",
        "what would you like",
        "what do you want",
        "can i help you",
        "what can i do",
        "how can i help",
    ]
    has_options = (" or " in last_q) or ("," in last_q and len(last_q.split(",")) >= 2)
    for phrase in generic:
        if phrase in last_q and not has_options:
            return f"PERGUNTA GENERICA sem opcoes: {last_q!r}"
    return None


def detect_high_latency(latency_ms: int, mode: str) -> str | None:
    # Simulator = conversa; limite mais apertado
    limit = 3500 if mode == "simulator" else 4500
    if latency_ms > limit:
        return f"LATENCIA ALTA: {latency_ms}ms (limite {limit}ms em modo {mode})"
    return None


def detect_vocab_above_level(ai_text: str, level: str) -> str | None:
    if level != "beginner":
        return None
    hard_words = [
        "accommodation", "amenities", "prescription", "certainly", "itinerary",
        "premise", "inquire", "comprehensive", "simultaneously", "subsequently",
        "accordingly", "reservation",  # reservation é B1+
    ]
    lower = (ai_text or "").lower()
    hit = [w for w in hard_words if re.search(rf"\b{w}\b", lower)]
    if hit:
        return f"VOCABULARIO ACIMA DE A1 em resposta beginner: {hit}"
    return None


def detect_meaning_drift(correction: dict | None) -> str | None:
    if not correction or not isinstance(correction, dict):
        return None
    wrong = str(correction.get("wrong") or "").lower()
    right = str(correction.get("right") or "").lower()
    if not wrong or not right or len(right.split()) < 3:
        return None
    wrong_keywords = [w for w in re.findall(r"\w+", wrong) if len(w) > 3]
    right_keywords = set(re.findall(r"\w+", right))
    if not wrong_keywords:
        return None
    overlap = sum(1 for w in wrong_keywords if w in right_keywords)
    ratio = overlap / len(wrong_keywords)
    if ratio < 0.25:
        return (
            f"CORRECAO PODE TER MUDADO O SIGNIFICADO. wrong={wrong!r} "
            f"right={right!r} (overlap: {int(ratio*100)}%)"
        )
    return None


def detect_interview_style(ai_text: str) -> str | None:
    # Resposta curta composta APENAS de pergunta é sinal de "entrevistadora"
    a = (ai_text or "").strip()
    if len(a) < 25 and a.endswith("?"):
        return f"RESPOSTA-ENTREVISTA: IA respondeu so com pergunta curta ({a!r})"
    return None


def detect_context_mix(ai_text: str, scenario: str) -> str | None:
    if scenario in ("free_conversation", "basic_structures"):
        return None
    cross = {
        "coffee_shop": ["deposit", "withdraw", "passport", "boarding gate"],
        "restaurant": ["deposit", "withdraw", "passport", "boarding gate"],
        "bakery": ["deposit", "withdraw", "passport", "boarding gate"],
        "bank": ["coffee", "latte", "cappuccino", "menu", "pizza", "croissant"],
        "hotel": ["coffee menu", "latte"],
        "airport": ["coffee menu"],
        "doctor": ["coffee", "menu", "deposit"],
        "pharmacy": ["coffee", "deposit"],
    }
    wrong_words = cross.get(scenario, [])
    lower = (ai_text or "").lower()
    hit = [w for w in wrong_words if w in lower]
    if hit:
        return f"CONTEXTO MISTURADO no cenario {scenario}: palavras {hit}"
    return None


def reanalyze(data: list[dict]) -> list[dict]:
    for r in data:
        r["total_violations"] = 0
        for t in r["turns"]:
            violations = []
            # 1. IA ignorou pergunta (detector melhor)
            if detect_ia_ignored_question(t["user_text"], t["ai_text"]):
                violations.append(
                    f"IA IGNOROU a pergunta do aluno. Aluno: {t['user_text']!r}. "
                    f"Resposta nao responde: {t['ai_text'][:120]!r}"
                )
            # 2. Correção mudou significado
            v = detect_meaning_drift(t.get("turn_correction"))
            if v: violations.append(v)
            # 3. Pergunta follow-up genérica
            v = detect_generic_followup(t["ai_text"], t["user_text"], r["mode"])
            if v: violations.append(v)
            # 4. Vocabulário acima do nível
            v = detect_vocab_above_level(t["ai_text"], r["level"])
            if v: violations.append(v)
            # 5. Contexto misturado
            v = detect_context_mix(t["ai_text"], r["scenario"])
            if v: violations.append(v)
            # 6. Latência alta
            v = detect_high_latency(t["latency_ms"], r["mode"])
            if v: violations.append(v)
            # 7. Entrevistadora
            v = detect_interview_style(t["ai_text"])
            if v: violations.append(v)

            t["violations"] = violations
            r["total_violations"] += len(violations)
    return data


def generate_html_report(results: list[dict]) -> str:
    from collections import Counter
    total_tests = len(results)
    total_turns = sum(len(r["turns"]) for r in results)
    total_violations = sum(r["total_violations"] for r in results)
    passed = sum(1 for r in results if r["total_violations"] == 0 and not r.get("error"))

    cat_counter: Counter[str] = Counter()
    for r in results:
        for t in r["turns"]:
            for v in t["violations"]:
                key = v.split(":", 1)[0].split("(")[0].strip()
                key = " ".join(key.split()[0:4])
                cat_counter[key] += 1

    grouped_html = ""
    for cat, count in cat_counter.most_common():
        grouped_html += f'<li><strong>{cat}</strong> — {count} ocorr&ecirc;ncia{"s" if count != 1 else ""}</li>'
    if not grouped_html:
        grouped_html = "<li>Nenhuma viola&ccedil;&atilde;o detectada 🎉</li>"

    # Cards por teste
    test_cards_html = ""
    for r in results:
        color = "#E76F51" if (r["total_violations"] > 0 or r.get("error")) else "#7FB069"
        status = "FALHOU" if (r["total_violations"] > 0 or r.get("error")) else "OK"
        error_html = f'<div class="error-box">Erro: {r["error"]}</div>' if r.get("error") else ""
        turns_html = ""
        for t in r["turns"]:
            v_html = ""
            if t["violations"]:
                v_html = '<div class="violations">' + "".join(
                    f'<div class="violation">&#9888; {v}</div>' for v in t["violations"]
                ) + '</div>'
            correction_html = ""
            if t.get("turn_correction"):
                w = t["turn_correction"].get("wrong", "")
                rg = t["turn_correction"].get("right", "")
                correction_html = (
                    f'<div class="correction"><em>correction:</em> wrong="{w}" &rarr; right="{rg}"</div>'
                )
            turns_html += f"""
            <div class="turn {'has-violations' if t['violations'] else ''}">
                <div class="turn-head">Turno {t['turn']} &middot; {t['latency_ms']}ms</div>
                <div class="user"><strong>&#128100;</strong> {t['user_text']}</div>
                <div class="ai"><strong>&#129302;</strong> {t['ai_text']}</div>
                {correction_html}
                {v_html}
            </div>"""
        test_cards_html += f"""
        <details class="test-card" {'open' if r['total_violations'] > 0 else ''}>
            <summary style="border-left:4px solid {color};">
                <span style="color:{color}; font-weight:700;">{status}</span> &middot;
                Teste #{r['test_id']:02d} &mdash;
                <strong>{r['scenario']}</strong> &middot; {r['level']} &middot; {r['mode']} &middot;
                {r['total_violations']} viola&ccedil;&otilde;es
            </summary>
            {error_html}
            <div class="turns">{turns_html}</div>
        </details>"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Auditoria Pedag&oacute;gica &mdash; IA de Conversa&ccedil;&atilde;o v2.0</title>
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
<h1>&#128269; Auditoria Pedag&oacute;gica &mdash; IA de Conversa&ccedil;&atilde;o v2.0</h1>
<div class="meta">Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &middot;
Persona: Whesley (product owner) &middot; Detectores refinados (v2)</div>

<div class="overview">
  <div class="stat"><div class="n">{total_tests}</div><div class="l">testes executados</div></div>
  <div class="stat"><div class="n">{total_turns}</div><div class="l">turnos analisados</div></div>
  <div class="stat"><div class="n" style="color:#7FB069">{passed}</div><div class="l">testes sem viola&ccedil;&otilde;es</div></div>
  <div class="stat"><div class="n" style="color:#E76F51">{total_tests - passed}</div><div class="l">testes com viola&ccedil;&otilde;es</div></div>
  <div class="stat"><div class="n" style="color:#E76F51">{total_violations}</div><div class="l">viola&ccedil;&otilde;es totais</div></div>
</div>

<div class="section">
  <h2>&#128202; Viola&ccedil;&otilde;es por categoria</h2>
  <ul>{grouped_html}</ul>
</div>

<div class="section">
  <h2>&#129514; Detalhe dos testes</h2>
  <p style="color:#A8B5C0; font-size:0.85rem;">Clique em cada teste para ver a transcri&ccedil;&atilde;o completa e viola&ccedil;&otilde;es por turno. Testes com viola&ccedil;&atilde;o j&aacute; v&ecirc;m abertos.</p>
  {test_cards_html}
</div>
</body>
</html>"""


def main():
    src = ROOT / "audit_report.json"
    if not src.exists():
        raise SystemExit(f"audit_report.json nao encontrado em {src}")
    data = json.loads(src.read_text(encoding="utf-8"))
    data = reanalyze(data)
    html = generate_html_report(data)
    out = ROOT / "audit_report.html"
    out.write_text(html, encoding="utf-8")
    (ROOT / "audit_report.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Relatorio atualizado: {out}")
    total_v = sum(r["total_violations"] for r in data)
    print(f"Violacoes com detector refinado: {total_v}")
    # abre no browser
    try:
        import webbrowser
        webbrowser.open(out.as_uri())
    except Exception:
        pass


if __name__ == "__main__":
    main()
