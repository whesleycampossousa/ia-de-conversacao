#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversation Orchestrator - Sistema de orquestração de conversas didáticas
Implementa intent router, FSM, handlers e anti-loop para modo professor IA
"""

import re
import json
from typing import Dict, List, Optional, Tuple
from enum import Enum

# Importa classes do orchestrator
from conversation_orchestrator import (
    Intent, Phase, LanguageMode, LessonSpec, SessionState,
    detect_intent, choose_policy_action, on_student_message
)

# ============================================================================
# ENUMS E CONSTANTES
# ============================================================================

class Intent(Enum):
    GREETING_OR_THANKS = "greeting_or_thanks"
    META_UNDERSTANDING = "meta_understanding"
    ASK_BOT_OPINION = "ask_bot_opinion"
    ASK_GRAMMAR_HELP = "ask_grammar_help"
    STUDENT_ANSWER = "student_answer"
    CONFUSION_OR_FRUSTRATION = "confusion_or_frustration"
    OFF_TOPIC = "off_topic"
    REQUEST_LANGUAGE_MODE = "request_language_mode"
    REQUEST_STOP_OR_CHANGE = "request_stop_or_change"

class Phase(Enum):
    INTRO = "INTRO"
    TEACH = "TEACH"
    PRACTICE = "PRACTICE"
    FEEDBACK = "FEEDBACK"
    REVIEW = "REVIEW"

class LanguageMode(Enum):
    PT = "pt"
    EN = "en"
    BILINGUAL = "bilingual"

# ============================================================================
# MODELOS DE DADOS
# ============================================================================

class MicroGoal:
    def __init__(self, data: Dict):
        self.id = data.get('id', '')
        self.explanation_pt = data.get('explanation_pt', '')
        self.rule_pt = data.get('rule_pt', '')
        self.examples = data.get('examples', [])
        self.practice_prompts = data.get('practice_prompts', [])
        self.common_errors = data.get('common_errors', [])

class LessonSpec:
    def __init__(self, data: Dict):
        self.topic_id = data.get('topic_id', '')
        self.title_pt = data.get('title_pt', '')
        self.level = data.get('level', 'beginner')
        self.language_mode = LanguageMode(data.get('language_mode', 'bilingual'))
        self.micro_goals = [MicroGoal(mg) for mg in data.get('micro_goals', [])]
        self.constraints = data.get('constraints', {
            'max_lines_before_question': 4,
            'allow_portuguese_correction': False,
            'correction_style': 'minimal',
            'end_turn_must_ask_question': True
        })

class SessionState:
    def __init__(self):
        self.step_index = 0
        self.phase = Phase.INTRO
        self.last_bot_question = ""
        self.last_target = ""
        self.last_student_intent = ""
        self.is_learning_mode = True  # SEMPRE True quando usando orchestrator (é modo Aprendizado)
        self.is_first_message = True  # Flag para detectar primeira mensagem
        self.topic_name = ""  # Nome do tema escolhido
        self.student_pref = {
            'language_mode': LanguageMode.BILINGUAL,
            'wants_corrections': True,
            'wants_portuguese_help': True
        }
        self.error_log = []
        self.safety = {
            'loop_counter': 0,
            'repeated_bot_phrase_counter': {},
            'last_3_bot_intents': []
        }

# ============================================================================
# INTENT ROUTER
# ============================================================================

def normalize_text(text: str) -> str:
    """Normaliza texto para comparação"""
    if not text:
        return ""
    text = text.lower().strip()
    # Remove pontuação excessiva
    text = re.sub(r'[^\w\s]', ' ', text)
    # Remove espaços múltiplos
    text = re.sub(r'\s+', ' ', text)
    return text

def is_short_thanks_or_greeting(text: str) -> bool:
    """Verifica se é um cumprimento/agradecimento curto"""
    if len(text) > 20:
        return False
    
    greetings = [
        'oi', 'olá', 'hello', 'hi', 'hey',
        'obrigado', 'obrigada', 'thanks', 'thank you', 'valeu',
        'de nada', 'you\'re welcome', 'no problem',
        'tchau', 'bye', 'see you'
    ]
    
    normalized = normalize_text(text)
    return any(g in normalized for g in greetings)

def looks_like_answer_attempt(text: str) -> bool:
    """Verifica se parece uma tentativa de resposta"""
    normalized = normalize_text(text)
    
    # Tokens em inglês comuns em respostas
    en_tokens = ['i', 'am', 'is', 'are', 'i\'m', 'you', 'are', 'he', 'she', 'it', 'we', 'they']
    if any(token in normalized for token in en_tokens):
        return True
    
    # Tentativas em português descrevendo significado
    pt_attempts = ['eu estou', 'me sinto', 'estou feliz', 'estou cansado', 'estou triste']
    if any(attempt in normalized for attempt in pt_attempts):
        return True
    
    # Palavras-chave de estados/emoções
    emotion_words = ['happy', 'tired', 'sad', 'excited', 'good', 'bad', 'feliz', 'cansado', 'triste']
    if any(word in normalized for word in emotion_words):
        return True
    
    return False

def detect_intent(text: str) -> Intent:
    """
    Classifica a intenção do aluno usando heurísticas simples
    """
    if not text:
        return Intent.OFF_TOPIC
    
    t = normalize_text(text)
    
    # REQUEST_LANGUAGE_MODE
    if any(phrase in t for phrase in ['português', 'portugues', 'só inglês', 'so ingles', 'bilingue', 'bilíngue', 'bilingual']):
        return Intent.REQUEST_LANGUAGE_MODE
    
    # META_UNDERSTANDING
    if any(phrase in t for phrase in ['você entendeu', 'vc entendeu', 'entendeu o que eu disse', 'did you understand', 'understand what i said']):
        return Intent.META_UNDERSTANDING
    
    # ASK_BOT_OPINION
    if any(phrase in t for phrase in ['e você', 'and you', 'what about you', 'how about you', 'or you', 'your opinion', 'qual sua opinião', 'what do you think']):
        return Intent.ASK_BOT_OPINION
    
    # CONFUSION_OR_FRUSTRATION
    if any(phrase in t for phrase in ['não respondeu', 'você não respondeu', 'desastre', 'errado', 'não é isso', 'confuso', 'didn\'t answer', 'wrong', 'confused']):
        return Intent.CONFUSION_OR_FRUSTRATION
    
    # GREETING_OR_THANKS
    if is_short_thanks_or_greeting(text):
        return Intent.GREETING_OR_THANKS
    
    # ASK_GRAMMAR_HELP
    if any(phrase in t for phrase in ['como fala', 'como digo', 'qual regra', 'por que', 'when do i use', 'grammar', 'como usar', 'how do i say']):
        return Intent.ASK_GRAMMAR_HELP
    
    # REQUEST_STOP_OR_CHANGE
    if any(phrase in t for phrase in ['trocar', 'próxima', 'mudar tema', 'stop', 'change topic', 'next', 'próximo']):
        return Intent.REQUEST_STOP_OR_CHANGE
    
    # STUDENT_ANSWER
    if looks_like_answer_attempt(text):
        return Intent.STUDENT_ANSWER
    
    # OFF_TOPIC (padrão)
    return Intent.OFF_TOPIC

# ============================================================================
# POLICY ENGINE
# ============================================================================

def choose_policy_action(intent: Intent, session_state: SessionState) -> str:
    """
    Define a ação baseada na intenção e estado da sessão
    Prioridades nunca quebram
    """
    # PRIORIDADE 1: Pergunta do aluno sempre vem antes
    if intent in [Intent.ASK_BOT_OPINION, Intent.META_UNDERSTANDING, Intent.ASK_GRAMMAR_HELP]:
        return "ANSWER_STUDENT_QUESTION_THEN_RETURN_TO_LESSON"
    
    # PRIORIDADE 2: Frustração/confusão
    if intent == Intent.CONFUSION_OR_FRUSTRATION:
        return "DEESCALATE_CLARIFY_AND_REPAIR"
    
    # PRIORIDADE 3: Request language mode
    if intent == Intent.REQUEST_LANGUAGE_MODE:
        return "SET_LANGUAGE_MODE"
    
    # PRIORIDADE 4: Obrigado/oi
    if intent == Intent.GREETING_OR_THANKS:
        return "ACK_AND_REDIRECT_TO_PRACTICE"
    
    # PRIORIDADE 5: Resposta do aluno
    if intent == Intent.STUDENT_ANSWER:
        return "EVALUATE_AND_FEEDBACK"
    
    # OFF_TOPIC
    if intent == Intent.OFF_TOPIC:
        return "GENTLE_REDIRECT"
    
    if intent == Intent.REQUEST_STOP_OR_CHANGE:
        return "OFFER_OPTIONS"
    
    return "GENTLE_REDIRECT"

# ============================================================================
# FORMATADORES DE SAÍDA
# ============================================================================

def out_pt(s: str) -> str:
    """Formata texto em português"""
    return s

def out_en(s: str) -> str:
    """Formata texto em inglês com tags [EN]"""
    return f"[EN]{s}[/EN]"

def format_bilingual(pt: str, en: Optional[str] = None, pt2: Optional[str] = None, mode: LanguageMode = LanguageMode.BILINGUAL) -> str:
    """
    Formata mensagem bilíngue baseado no modo de linguagem
    """
    if mode == LanguageMode.PT:
        result = pt
        if pt2:
            result += " " + pt2
        return result
    
    if mode == LanguageMode.EN:
        if en:
            return en
        # Se não tem EN, retorna PT traduzido (simplificado - em produção usaria tradução real)
        return out_en(pt)
    
    # BILINGUAL
    msg = pt
    if en:
        msg += "\n" + out_en(en)
    if pt2:
        msg += "\n" + pt2
    return msg

def finalize_turn(text: str, question: str, lesson_spec: LessonSpec) -> str:
    """
    Finaliza turno com pergunta obrigatória
    """
    # Limitar tamanho
    lines = text.split('\n')
    max_lines = lesson_spec.constraints.get('max_lines_before_question', 4)
    if len(lines) > max_lines:
        text = '\n'.join(lines[:max_lines])
    
    # Sempre finalizar com pergunta
    if lesson_spec.constraints.get('end_turn_must_ask_question', True):
        return text + "\n" + question
    
    return text

def pick_variant(key: str, variants: List[str], session_state: SessionState) -> str:
    """
    Escolhe variante evitando repetições recentes
    """
    counter = session_state.safety.repeated_bot_phrase_counter
    if key not in counter:
        counter[key] = {}
    
    # Escolhe variante menos usada recentemente
    variant_counts = counter[key]
    if not variant_counts:
        chosen = variants[0]
    else:
        # Escolhe a variante com menor contagem
        chosen = min(variants, key=lambda v: variant_counts.get(v, 0))
    
    # Incrementa contador
    variant_counts[chosen] = variant_counts.get(chosen, 0) + 1
    
    return chosen

# ============================================================================
# AVALIAÇÃO DE RESPOSTA DO ALUNO
# ============================================================================

def infer_meaning(text: str) -> str:
    """
    Infere o significado da resposta do aluno (PT ou EN)
    """
    normalized = normalize_text(text)
    
    # Mapeamento de palavras de emoção/estado
    emotion_map = {
        'happy': 'feliz',
        'tired': 'cansado',
        'sad': 'triste',
        'excited': 'animado',
        'good': 'bem',
        'bad': 'mal',
        'feliz': 'feliz',
        'cansado': 'cansado',
        'triste': 'triste',
        'animado': 'animado'
    }
    
    for word, meaning in emotion_map.items():
        if word in normalized:
            return meaning
    
    return "algo positivo"  # fallback

def extract_or_infer_english_attempt(text: str) -> Optional[str]:
    """
    Extrai ou infere tentativa em inglês do aluno
    """
    normalized = normalize_text(text)
    
    # Procura padrões como "I am happy", "I'm tired", etc.
    patterns = [
        r'i\s+am\s+(\w+)',
        r'i\'m\s+(\w+)',
        r'i\s+(\w+)',  # "I happy" (erro comum)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            adj = match.group(1)
            return f"I am {adj}"
    
    return None

def meaning_to_pt(meaning: str) -> str:
    """Converte significado para português"""
    return meaning

def evaluate_answer(student_text: str, micro_goal: MicroGoal) -> Dict:
    """
    Avalia resposta do aluno
    """
    meaning = infer_meaning(student_text)
    produced_en = extract_or_infer_english_attempt(student_text)
    
    errors = []
    
    # Verifica erros comuns baseado no micro_goal
    if micro_goal.id == "to_be_i_am":
        normalized = normalize_text(student_text)
        # Erro: falta "am" depois de "I"
        if re.search(r'\bi\s+(happy|tired|sad|good|bad|excited)\b', normalized):
            errors.append({
                'type': 'missing_be',
                'fix': f"I am {meaning}",
                'tip_pt': "Faltou o 'am' depois de 'I'."
            })
    
    return {
        'meaning': meaning,
        'produced_en': produced_en,
        'errors': errors
    }

# ============================================================================
# HANDLERS
# ============================================================================

def handle_question(intent: Intent, student_text: str, lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Responde pergunta do aluno e retorna à lição
    REGRA CRÍTICA: No modo learning, SEMPRE retoma o tema após responder
    """
    mode = session_state.student_pref['language_mode']
    
    # Pega micro_goal atual
    current_micro_goal = None
    if session_state.step_index < len(lesson_spec.micro_goals):
        current_micro_goal = lesson_spec.micro_goals[session_state.step_index]
    else:
        current_micro_goal = lesson_spec.micro_goals[0] if lesson_spec.micro_goals else None
    
    if intent == Intent.META_UNDERSTANDING:
        # Parafraseia o que entendeu E retoma o tema
        guess = "Você respondeu de forma educada e eu gostei disso."
        current_example = "I am happy."
        if current_micro_goal and current_micro_goal.examples:
            current_example = current_micro_goal.examples[0].get('en', 'I am happy.')
        
        base = format_bilingual(
            f"Entendi sim 👍 {guess}",
            None,
            f"E já estamos praticando exatamente isso no tema {lesson_spec.title_pt}.",
            mode
        )
        # Mostra exemplo do tema
        if current_micro_goal and current_micro_goal.examples:
            example = current_micro_goal.examples[0]
            base += "\n" + format_bilingual(
                f"Quando você diz como está, em inglês fica:",
                example.get('en', ''),
                mode=mode
            )
        # Prática guiada
        if current_micro_goal and current_micro_goal.practice_prompts:
            prompt = current_micro_goal.practice_prompts[0]
            q = format_bilingual(
                prompt.get('pt', 'Agora tente você: como está hoje?'),
                prompt.get('target_en_hint', 'I am ___.'),
                mode=mode
            )
        else:
            q = format_bilingual(
                "Agora tente: como você está hoje?",
                "Now try: How are you today? Say: I am ___.",
                mode=mode
            )
        return finalize_turn(base, q, lesson_spec)
    
    if intent == Intent.ASK_BOT_OPINION:
        # Responde E retoma o tema
        bot_answer_en = "I am good today. I am a bit tired."
        base = format_bilingual(
            "Boa! Eu também respondo 😊",
            bot_answer_en,
            f"E já estamos praticando exatamente isso no tema {lesson_spec.title_pt}.",
            mode
        )
        # Mostra exemplo
        if current_micro_goal and current_micro_goal.examples:
            example = current_micro_goal.examples[0]
            base += "\n" + format_bilingual(
                f"Quando você diz como está, em inglês fica:",
                example.get('en', ''),
                mode=mode
            )
        # Prática guiada
        if current_micro_goal and current_micro_goal.practice_prompts:
            prompt = current_micro_goal.practice_prompts[0]
            q = format_bilingual(
                prompt.get('pt', 'Agora é sua vez: como está hoje?'),
                prompt.get('target_en_hint', 'I am ___.'),
                mode=mode
            )
        else:
            q = format_bilingual(
                "Agora é sua vez: como está hoje?",
                "Now your turn: How are you today? Say: I am ___.",
                mode=mode
            )
        return finalize_turn(base, q, lesson_spec)
    
    if intent == Intent.ASK_GRAMMAR_HELP:
        # Explica E retoma o tema
        if current_micro_goal:
            rule = current_micro_goal.rule_pt or "usamos o verbo 'to be' antes do adjetivo"
            base = format_bilingual(
                f"Claro! A regra aqui é simples: {rule}.",
                current_micro_goal.rule_pt if current_micro_goal.rule_pt else "I am + adjective.",
                None,
                mode
            )
            # Mostra exemplos
            if current_micro_goal.examples:
                for example in current_micro_goal.examples[:2]:  # Máximo 2 exemplos
                    base += "\n" + format_bilingual(
                        f"Ex.:",
                        example.get('en', ''),
                        mode=mode
                    )
        else:
            base = format_bilingual(
                "Claro! A regra aqui é simples: usamos o verbo 'to be' antes do adjetivo.",
                "I am + adjective. / You are + adjective.",
                "Ex.: I am happy. / You are tired.",
                mode
            )
        # Prática guiada
        if current_micro_goal and current_micro_goal.practice_prompts:
            prompt = current_micro_goal.practice_prompts[0]
            q = format_bilingual(
                prompt.get('pt', 'Agora tente: como está hoje?'),
                prompt.get('target_en_hint', 'I am ___.'),
                mode=mode
            )
        else:
            q = format_bilingual(
                "Agora tente uma: 'Eu estou feliz' em inglês 😊",
                "Now try: 'I am happy.'",
                mode=mode
            )
        return finalize_turn(base, q, lesson_spec)
    
    # Fallback genérico (não deveria acontecer)
    return format_bilingual(
        f"Entendi sua pergunta! Vamos continuar praticando {lesson_spec.title_pt}.",
        "I understand! Let's continue practicing.",
        mode=mode
    )

def handle_frustration(student_text: str, lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Desescala frustração e clarifica
    REGRA: No modo learning, SEMPRE retoma o tema explicitamente
    """
    mode = session_state.student_pref['language_mode']
    
    # Detecta se aluno está questionando sobre o tema
    normalized = normalize_text(student_text)
    if any(phrase in normalized for phrase in ['já sabe', 'já tá', 'já estamos', 'dentro de um tema', 'tema']):
        # Aluno está questionando se a IA sabe o tema - CONFIRMA e retoma
        base = format_bilingual(
            f"Isso mesmo 😊 Estamos no tema {lesson_spec.title_pt}, e eu vou te guiar passo a passo.",
            None,
            f"Vamos continuar praticando {lesson_spec.title_pt}.",
            mode
        )
        # Mostra exemplo do tema
        current_micro_goal = lesson_spec.micro_goals[0] if lesson_spec.micro_goals else None
        if current_micro_goal and current_micro_goal.examples:
            example = current_micro_goal.examples[0]
            base += "\n" + format_bilingual(
                f"Lembra:",
                example.get('en', ''),
                mode=mode
            )
        # Prática guiada
        if current_micro_goal and current_micro_goal.practice_prompts:
            prompt = current_micro_goal.practice_prompts[0]
            q = format_bilingual(
                prompt.get('pt', 'Vamos continuar. Como está hoje?'),
                prompt.get('target_en_hint', 'I am ___.'),
                mode=mode
            )
        else:
            q = format_bilingual(
                "Vamos continuar 👇",
                "Let's continue:",
                mode=mode
            )
        return finalize_turn(base, q, lesson_spec)
    
    # Frustração genérica
    base = format_bilingual(
        f"Entendi 🙏 Vamos ajustar isso rapidinho. Estamos no tema {lesson_spec.title_pt}, e eu vou te guiar passo a passo.",
        None,
        f"Vamos continuar praticando {lesson_spec.title_pt}.",
        mode
    )
    # Prática guiada
    current_micro_goal = lesson_spec.micro_goals[0] if lesson_spec.micro_goals else None
    if current_micro_goal and current_micro_goal.practice_prompts:
        prompt = current_micro_goal.practice_prompts[0]
        q = format_bilingual(
            prompt.get('pt', 'Vamos continuar. Como está hoje?'),
            prompt.get('target_en_hint', 'I am ___.'),
            mode=mode
        )
    else:
        q = format_bilingual(
            "Vamos continuar 👇",
            "Let's continue:",
            mode=mode
        )
    return finalize_turn(base, q, lesson_spec)

def handle_thanks_or_greeting(lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Reconhece agradecimento/cumprimento e redireciona para prática
    REGRA: No modo learning, SEMPRE retoma o tema
    """
    mode = session_state.student_pref['language_mode']
    ack_pt = pick_variant("ack", ["De nada 😊", "Imagina! 😊", "Sempre! 😊"], session_state)
    ack_en = pick_variant("ack_en", ["You're welcome 😊", "No problem 😊", "Anytime 😊"], session_state)
    
    # NO MODO LEARNING: Sempre retoma o tema
    if session_state.is_learning_mode:
        # Pega micro_goal atual
        current_micro_goal = None
        if session_state.step_index < len(lesson_spec.micro_goals):
            current_micro_goal = lesson_spec.micro_goals[session_state.step_index]
        else:
            current_micro_goal = lesson_spec.micro_goals[0] if lesson_spec.micro_goals else None
        
        if current_micro_goal and current_micro_goal.practice_prompts:
            prompt = current_micro_goal.practice_prompts[0]
            base = format_bilingual(
                f"{ack_pt} Então vamos usar isso no {lesson_spec.title_pt}.",
                None,
                f"Quando você quer dizer como está, usamos o verbo to be.",
                mode
            )
            # Mostra exemplo
            if current_micro_goal.examples:
                example = current_micro_goal.examples[0]
                base += "\n" + format_bilingual(
                    f"Exemplo:",
                    example.get('en', ''),
                    mode=mode
                )
            q = format_bilingual(
                prompt.get('pt', 'Como você está hoje?'),
                prompt.get('target_en_hint', 'I am ___.'),
                mode=mode
            )
            return finalize_turn(base, q, lesson_spec)
    
    # Fallback genérico (não deveria acontecer no modo learning)
    base = format_bilingual(ack_pt, ack_en, mode=mode)
    q = format_bilingual(
        "Vamos praticar: como você está hoje?",
        "Let's practice: How are you today? Say: I am ___.",
        mode=mode
    )
    return finalize_turn(base, q, lesson_spec)

def handle_student_answer(student_text: str, lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Avalia resposta do aluno e dá feedback
    REGRA: No modo learning, SEMPRE retoma o tema após feedback
    """
    mode = session_state.student_pref['language_mode']
    
    # Pega micro_goal atual
    current_micro_goal = None
    if session_state.step_index < len(lesson_spec.micro_goals):
        current_micro_goal = lesson_spec.micro_goals[session_state.step_index]
    else:
        current_micro_goal = lesson_spec.micro_goals[-1] if lesson_spec.micro_goals else None
    
    if not current_micro_goal:
        return format_bilingual(
            f"Vamos continuar praticando {lesson_spec.title_pt}!",
            "Let's continue practicing!",
            mode=mode
        )
    
    result = evaluate_answer(student_text, current_micro_goal)
    
    # Confirmação de sentido
    confirm_pt = f"Perfeito, entendi 👍 Você quer dizer que {meaning_to_pt(result['meaning'])}."
    
    # Feedback
    if not result['errors']:
        praise_pt = pick_variant("praise", ["Muito bom!", "Excelente!", "Boa!", "Mandou bem!"], session_state)
        produced_en = result['produced_en'] or f"I am {result['meaning']}"
        base = format_bilingual(
            f"{praise_pt} {confirm_pt}",
            produced_en,
            f"E já estamos praticando exatamente isso no tema {lesson_spec.title_pt}.",
            mode
        )
        # Próxima pergunta de prática (sempre relacionada ao tema)
        next_prompt = current_micro_goal.practice_prompts[0] if current_micro_goal.practice_prompts else {}
        q = format_bilingual(
            next_prompt.get('pt', 'Agora vamos fazer mais uma bem parecida. Como você está?'),
            next_prompt.get('target_en_hint', 'I am ___.'),
            mode=mode
        )
        return finalize_turn(base, q, lesson_spec)
    
    # Tem erro - corrige E retoma o tema
    e = result['errors'][0]
    praise_pt = pick_variant("praise2", ["Muito bom!", "Boa tentativa!", "Tá indo bem!"], session_state)
    corrected_en = e['fix']
    base = format_bilingual(
        f"{praise_pt} {confirm_pt}",
        corrected_en,
        f"{e['tip_pt']} Vamos tentar de novo rapidinho 😊",
        mode
    )
    # Prática guiada com exemplo do tema
    q = format_bilingual(
        "Agora tente montar a frase comigo 😊",
        "Now try to build the sentence with me:",
        mode=mode
    )
    if current_micro_goal and current_micro_goal.examples:
        example = current_micro_goal.examples[0]
        q += "\n" + format_bilingual(
            f"Complete:",
            example.get('en', '').replace(example.get('en', '').split()[-1], '___'),
            mode=mode
        )
    if mode == LanguageMode.BILINGUAL:
        q += "\n" + out_en(e['fix'] + ".")
    return finalize_turn(base, q, lesson_spec)

def handle_off_topic(lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Redireciona gentilmente para o tema
    REGRA CRÍTICA: No modo learning, SEMPRE menciona o tema explicitamente
    """
    mode = session_state.student_pref['language_mode']
    base = format_bilingual(
        f"Tranquilo 😊 Estamos no tema {lesson_spec.title_pt}, e eu vou te guiar passo a passo.",
        None,
        f"Vamos continuar praticando {lesson_spec.title_pt}.",
        mode
    )
    # Pega prompt atual
    current_micro_goal = None
    if session_state.step_index < len(lesson_spec.micro_goals):
        current_micro_goal = lesson_spec.micro_goals[session_state.step_index]
    else:
        current_micro_goal = lesson_spec.micro_goals[0] if lesson_spec.micro_goals else None
    
    # Mostra exemplo do tema
    if current_micro_goal and current_micro_goal.examples:
        example = current_micro_goal.examples[0]
        base += "\n" + format_bilingual(
            f"Lembra:",
            example.get('en', ''),
            mode=mode
        )
    
    prompt_pt = current_micro_goal.practice_prompts[0].get('pt', 'Como você está?') if current_micro_goal and current_micro_goal.practice_prompts else "Como você está?"
    prompt_en = current_micro_goal.practice_prompts[0].get('target_en_hint', 'I am ___.') if current_micro_goal and current_micro_goal.practice_prompts else "I am ___."
    q = format_bilingual(prompt_pt, prompt_en, mode=mode)
    return finalize_turn(base, q, lesson_spec)

def handle_set_language_mode(student_text: str, lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Define modo de linguagem
    REGRA: No modo learning, SEMPRE retoma o tema após mudar idioma
    """
    t = normalize_text(student_text)
    new_mode = LanguageMode.BILINGUAL
    
    if 'português' in t or 'portugues' in t:
        new_mode = LanguageMode.PT
    elif 'inglês' in t or 'ingles' in t or 'english' in t:
        new_mode = LanguageMode.EN
    else:
        new_mode = LanguageMode.BILINGUAL
    
    session_state.student_pref['language_mode'] = new_mode
    mode = new_mode
    
    if new_mode == LanguageMode.PT:
        base = f"Fechado! Vou falar só em português e usar inglês só nos exemplos.\n\nVamos continuar com o tema {lesson_spec.title_pt}."
    elif new_mode == LanguageMode.EN:
        base = out_en(f"Great! We'll use English only (I can keep it simple).\n\nLet's continue with {lesson_spec.title_pt}.")
    else:
        base = f"Perfeito! Vamos em modo bilíngue: explico em PT e praticamos em EN.\n{out_en('Let's practice in English.')}\n\nVamos continuar com o tema {lesson_spec.title_pt}."
    
    # Mostra exemplo do tema
    current_micro_goal = None
    if session_state.step_index < len(lesson_spec.micro_goals):
        current_micro_goal = lesson_spec.micro_goals[session_state.step_index]
    else:
        current_micro_goal = lesson_spec.micro_goals[0] if lesson_spec.micro_goals else None
    
    if current_micro_goal and current_micro_goal.examples:
        example = current_micro_goal.examples[0]
        base += "\n" + format_bilingual(
            f"Lembra:",
            example.get('en', ''),
            mode=mode
        )
    
    # Prática guiada
    prompt_pt = current_micro_goal.practice_prompts[0].get('pt', 'Como você está?') if current_micro_goal and current_micro_goal.practice_prompts else "Como você está?"
    prompt_en = current_micro_goal.practice_prompts[0].get('target_en_hint', 'I am ___.') if current_micro_goal and current_micro_goal.practice_prompts else "I am ___."
    q = format_bilingual(prompt_pt, prompt_en, mode=mode)
    return finalize_turn(base, q, lesson_spec)

def handle_stop_or_change(lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Oferece opções quando aluno quer parar/trocar
    REGRA: No modo learning, sempre menciona o tema atual
    """
    mode = session_state.student_pref['language_mode']
    base = format_bilingual(
        f"Sem problema 😊 Estamos no tema {lesson_spec.title_pt}. O que você prefere agora?",
        None,
        f"1) Continuar mais 2 perguntas do tema {lesson_spec.title_pt}. 2) Trocar de tema. 3) Revisar do zero.",
        mode
    )
    q = format_bilingual(
        "Responde com 1, 2 ou 3.",
        "Reply with 1, 2, or 3.",
        mode=mode
    )
    return finalize_turn(base, q, lesson_spec)

# ============================================================================
# ANTI-LOOP / RECOVERY
# ============================================================================

def is_loop_risk(session_state: SessionState, intent: Intent) -> bool:
    """
    Detecta risco de loop
    """
    if session_state.safety['loop_counter'] >= 2:
        return True
    if session_state.safety['repeated_bot_phrase_counter'].get('choose_question', 0) >= 1:
        return True
    return False

def recover_from_loop(lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Recupera de loop
    """
    session_state.safety['loop_counter'] = 0
    mode = session_state.student_pref['language_mode']
    base = format_bilingual(
        "Foi mal — vou seguir a conversa com você direitinho agora 😊",
        None,
        "Vamos voltar pro exercício sem botões nem etapas.",
        mode
    )
    # Pega prompt atual
    current_micro_goal = None
    if session_state.step_index < len(lesson_spec.micro_goals):
        current_micro_goal = lesson_spec.micro_goals[session_state.step_index]
    prompt_pt = current_micro_goal.practice_prompts[0].get('pt', 'Como você está?') if current_micro_goal and current_micro_goal.practice_prompts else "Como você está?"
    prompt_en = current_micro_goal.practice_prompts[0].get('target_en_hint', 'I am ___.') if current_micro_goal and current_micro_goal.practice_prompts else "I am ___."
    q = format_bilingual(prompt_pt, prompt_en, mode=mode)
    return finalize_turn(base, q, lesson_spec)

# ============================================================================
# ORQUESTRADOR PRINCIPAL
# ============================================================================

def generate_intro_message(lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Gera mensagem de abertura para modo Aprendizado
    REGRA: SEMPRE menciona o tema escolhido explicitamente
    """
    mode = session_state.student_pref['language_mode']
    
    # Pega primeiro micro_goal
    first_micro_goal = lesson_spec.micro_goals[0] if lesson_spec.micro_goals else None
    
    # Abertura que SEMPRE menciona o tema
    intro_pt = f"Oi 😊\nVocê escolheu Aprendizado – {lesson_spec.title_pt}.\nHoje vamos usar o {lesson_spec.title_pt} para falar de como estamos nos sentindo."
    
    # Mostra exemplo
    example_text = ""
    if first_micro_goal and first_micro_goal.examples:
        example = first_micro_goal.examples[0]
        example_text = f"\n\nPor exemplo:\n{out_en(example.get('en', 'I am happy.'))} → {example.get('pt', 'Eu estou feliz.')}"
    
    # Prática guiada
    practice_text = "\n\nAgora vamos praticar juntos 👇"
    if first_micro_goal and first_micro_goal.practice_prompts:
        prompt = first_micro_goal.practice_prompts[0]
        question = format_bilingual(
            prompt.get('pt', 'Como você está hoje?'),
            prompt.get('target_en_hint', 'I am ___.'),
            mode=mode
        )
    else:
        question = format_bilingual(
            "Como você está hoje?",
            "How are you today? Say: I am ___.",
            mode=mode
        )
    
    full_intro = intro_pt + example_text + practice_text + "\n" + question
    
    # Marca que não é mais primeira mensagem
    session_state.is_first_message = False
    session_state.phase = Phase.PRACTICE
    
    return full_intro

def on_student_message(student_text: str, lesson_spec: LessonSpec, session_state: SessionState) -> str:
    """
    Processa mensagem do aluno e retorna resposta do professor
    REGRA CRÍTICA: Se é primeira mensagem, gera abertura com tema
    """
    # Se é primeira mensagem, gera abertura
    if session_state.is_first_message:
        return generate_intro_message(lesson_spec, session_state)
    
    # Detecta intenção
    intent = detect_intent(student_text)
    session_state.last_student_intent = intent.value
    
    # VALIDAÇÃO CRÍTICA: No modo learning, bloqueia perguntas genéricas
    if session_state.is_learning_mode:
        # Se detectou intenção que sugere pergunta genérica, força redirecionamento
        if intent == Intent.OFF_TOPIC:
            # No modo learning, OFF_TOPIC vira redirecionamento gentil para o tema
            return handle_off_topic(lesson_spec, session_state)
    
    # Anti-loop
    if is_loop_risk(session_state, intent):
        return recover_from_loop(lesson_spec, session_state)
    
    # Escolhe ação
    action = choose_policy_action(intent, session_state)
    
    # Executa handler
    if action == "ANSWER_STUDENT_QUESTION_THEN_RETURN_TO_LESSON":
        return handle_question(intent, student_text, lesson_spec, session_state)
    elif action == "DEESCALATE_CLARIFY_AND_REPAIR":
        return handle_frustration(student_text, lesson_spec, session_state)
    elif action == "SET_LANGUAGE_MODE":
        return handle_set_language_mode(student_text, lesson_spec, session_state)
    elif action == "ACK_AND_REDIRECT_TO_PRACTICE":
        return handle_thanks_or_greeting(lesson_spec, session_state)
    elif action == "EVALUATE_AND_FEEDBACK":
        return handle_student_answer(student_text, lesson_spec, session_state)
    elif action == "GENTLE_REDIRECT":
        return handle_off_topic(lesson_spec, session_state)
    elif action == "OFFER_OPTIONS":
        return handle_stop_or_change(lesson_spec, session_state)
    else:
        return handle_off_topic(lesson_spec, session_state)
