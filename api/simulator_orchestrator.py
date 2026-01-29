#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simulator Orchestrator - Sistema de roleplay realista
Implementa simulação de situações reais (hotel, banco, etc.) sem quebrar o roleplay
"""

import re
from typing import Dict, List, Optional
from enum import Enum

# ============================================================================
# ENUMS E CONSTANTES
# ============================================================================

class SimulatorIntent(Enum):
    CHECK_IN = "check_in"
    ASK_ROOM = "ask_room"
    REQUEST_VIEW = "request_view"
    ASK_CHECKOUT_TIME = "ask_checkout_time"
    PROVIDE_NAME = "provide_name"
    PROVIDE_RESERVATION = "provide_reservation"
    PROVIDE_DATES = "provide_dates"
    PROVIDE_ID = "provide_id"
    PROVIDE_PAYMENT = "provide_payment"
    REQUEST_SPECIAL = "request_special"
    CONFUSION = "confusion"
    OFF_TOPIC = "off_topic"
    ASK_FOR_TEACHING = "ask_for_teaching"
    RUDE_UNSAFE = "rude_unsafe"
    GREETING = "greeting"
    THANKS = "thanks"

class SimulatorStage(Enum):
    GREETING = 1
    RESERVATION_DETAILS = 2
    ID_AND_PAYMENT = 3
    ROOM_PREFERENCES = 4
    INFO_AND_CLOSING = 5
    OPTIONAL_ISSUES = 6

# ============================================================================
# MODELOS DE DADOS
# ============================================================================

class SimulatorState:
    def __init__(self):
        self.mode = "simulator"
        self.theme = "hotel"
        self.role = "front_desk"
        self.stage = SimulatorStage.GREETING
        self.language_mode = "en"
        self.last_user_intent = ""
        self.last_required_slot = "name"
        self.slots = {
            'name': None,
            'reservation': None,
            'dates': None,
            'id_confirmed': False,
            'payment_method': None,
            'preferences': {
                'view': None,
                'bed': None,
                'smoking': None
            }
        }
        self.flags = {
            'user_confused': False,
            'user_requested_teaching': False,
            'show_mini_feedback': False,
            'conversation_started': False
        }

# ============================================================================
# INTENT DETECTION PARA SIMULADOR
# ============================================================================

def normalize_text(text: str) -> str:
    """Normaliza texto para comparação"""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text

def detect_simulator_intent(text: str, stage: SimulatorStage, slots: Dict) -> SimulatorIntent:
    """
    Detecta intenção do aluno no contexto do simulador
    """
    if not text:
        return SimulatorIntent.CONFUSION
    
    t = normalize_text(text)
    
    # RUDE/UNSAFE - detectar primeiro
    unsafe_patterns = ['kill', 'die', 'hate', 'stupid', 'idiot', 'shut up']
    if any(pattern in t for pattern in unsafe_patterns):
        return SimulatorIntent.RUDE_UNSAFE
    
    # ASK_FOR_TEACHING
    if any(phrase in t for phrase in ['teach', 'ensina', 'explain', 'explica', 'how do i say', 'como falo']):
        return SimulatorIntent.ASK_FOR_TEACHING
    
    # GREETING/THANKS
    if any(phrase in t for phrase in ['hello', 'hi', 'hey', 'good morning', 'good evening', 'good afternoon']):
        return SimulatorIntent.GREETING
    if any(phrase in t for phrase in ['thank', 'thanks', 'obrigado', 'obrigada']):
        return SimulatorIntent.THANKS
    
    # CONFUSION
    if any(phrase in t for phrase in ['what', 'huh', 'sorry', 'repeat', 'again', 'não entendi', 'não entendi']):
        return SimulatorIntent.CONFUSION
    
    # PROVIDE_NAME
    if stage == SimulatorStage.GREETING or stage == SimulatorStage.RESERVATION_DETAILS:
        if any(phrase in t for phrase in ['my name is', 'i am', 'i\'m', 'meu nome é', 'eu sou']):
            return SimulatorIntent.PROVIDE_NAME
        if re.search(r'\b(name|nome)\b', t) and ('is' in t or 'é' in t):
            return SimulatorIntent.PROVIDE_NAME
    
    # PROVIDE_RESERVATION
    if stage == SimulatorStage.RESERVATION_DETAILS:
        if any(phrase in t for phrase in ['reservation', 'reserva', 'book', 'booked', 'i have']):
            return SimulatorIntent.PROVIDE_RESERVATION
    
    # PROVIDE_DATES
    if stage == SimulatorStage.RESERVATION_DETAILS:
        if any(phrase in t for phrase in ['check in', 'check out', 'stay', 'night', 'day', 'date']):
            return SimulatorIntent.PROVIDE_DATES
    
    # PROVIDE_ID
    if stage == SimulatorStage.ID_AND_PAYMENT:
        if any(phrase in t for phrase in ['id', 'passport', 'document', 'here', 'passcard', 'card']):
            return SimulatorIntent.PROVIDE_ID
    
    # PROVIDE_PAYMENT
    if stage == SimulatorStage.ID_AND_PAYMENT:
        if any(phrase in t for phrase in ['credit', 'card', 'cash', 'pay', 'payment', 'pagamento']):
            return SimulatorIntent.PROVIDE_PAYMENT
    
    # REQUEST_VIEW / ROOM PREFERENCES
    if stage == SimulatorStage.ROOM_PREFERENCES:
        if any(phrase in t for phrase in ['view', 'beach', 'city', 'ocean', 'window', 'vista']):
            return SimulatorIntent.REQUEST_VIEW
        if any(phrase in t for phrase in ['bed', 'king', 'single', 'double', 'twin']):
            return SimulatorIntent.ASK_ROOM
    
    # ASK_CHECKOUT_TIME
    if any(phrase in t for phrase in ['checkout', 'check out', 'leave', 'time', 'hour', 'when']):
        return SimulatorIntent.ASK_CHECKOUT_TIME
    
    # REQUEST_SPECIAL
    if any(phrase in t for phrase in ['late', 'early', 'wake up', 'breakfast', 'wifi', 'internet']):
        return SimulatorIntent.REQUEST_SPECIAL
    
    # OFF_TOPIC (se não se encaixa em nada acima)
    if stage.value > 1:  # Depois do greeting
        return SimulatorIntent.OFF_TOPIC
    
    # Default: assume tentativa de resposta
    return SimulatorIntent.CHECK_IN

# ============================================================================
# SLOT FILLING
# ============================================================================

def extract_slot_value(text: str, slot_type: str) -> Optional[str]:
    """
    Extrai valor do slot do texto do aluno
    """
    t = normalize_text(text)
    
    if slot_type == 'name':
        # Procura padrões como "my name is X", "I am X", "name is X"
        patterns = [
            r'my name is (\w+)',
            r'i am (\w+)',
            r'i\'m (\w+)',
            r'name is (\w+)',
            r'meu nome é (\w+)',
            r'eu sou (\w+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, t)
            if match:
                return match.group(1).title()
        # Se não encontrou padrão, tenta pegar última palavra como nome
        words = t.split()
        if len(words) > 2:
            return words[-1].title()
        return None
    
    elif slot_type == 'reservation':
        if 'yes' in t or 'sim' in t or 'have' in t:
            return 'yes'
        elif 'no' in t or 'não' in t or 'don\'t' in t:
            return 'no'
        return None
    
    elif slot_type == 'dates':
        # Procura por datas ou períodos
        if any(word in t for word in ['night', 'nights', 'day', 'days', 'week', 'weeks']):
            return 'extracted'
        return None
    
    elif slot_type == 'payment':
        if 'credit' in t or 'card' in t:
            return 'credit_card'
        elif 'cash' in t or 'dinheiro' in t:
            return 'cash'
        elif 'debit' in t:
            return 'debit_card'
        return None
    
    elif slot_type == 'view':
        if 'beach' in t or 'ocean' in t or 'mar' in t:
            return 'beach'
        elif 'city' in t or 'cidade' in t:
            return 'city'
        return None
    
    elif slot_type == 'bed':
        if 'king' in t:
            return 'king'
        elif 'single' in t or 'twin' in t:
            return 'twin'
        elif 'double' in t:
            return 'double'
        return None
    
    return None

# ============================================================================
# STAGE HANDLERS
# ============================================================================

def handle_stage_greeting(state: SimulatorState, theme: str = "hotel") -> str:
    """
    Stage 1: Greeting + Check-in opening
    """
    if not state.flags['conversation_started']:
        state.flags['conversation_started'] = True
        # Ajusta greeting baseado no tema
        if theme == "hotel":
            return "Good evening! Welcome to Sunset Hotel. Are you checking in?"
        elif theme == "bank":
            return "Good morning! Welcome to First National Bank. How can I help you today?"
        elif theme == "restaurant":
            return "Good evening! Welcome to our restaurant. Do you have a reservation?"
        else:
            return "Hello! How can I help you today?"
    return None

def handle_stage_reservation(state: SimulatorState, intent: SimulatorIntent, text: str) -> str:
    """
    Stage 2: Reservation details
    """
    if intent == SimulatorIntent.PROVIDE_NAME:
        name = extract_slot_value(text, 'name')
        if name:
            state.slots['name'] = name
            return f"Thank you, {name}. Do you have a reservation?"
        else:
            return "I didn't catch your name. Could you tell me your name, please?"
    
    if intent == SimulatorIntent.PROVIDE_RESERVATION:
        reservation = extract_slot_value(text, 'reservation')
        if reservation == 'yes':
            state.slots['reservation'] = True
            if state.slots['name']:
                return f"Perfect — a reservation under {state.slots['name']}. Could I see your ID, please?"
            else:
                return "Great! May I have your name, please?"
        elif reservation == 'no':
            state.slots['reservation'] = False
            return "No problem. Let me check what rooms we have available. How many nights will you be staying?"
        else:
            return "I'm not sure if you have a reservation. Do you have one, or would you like to book a room?"
    
    if intent == SimulatorIntent.CONFUSION:
        return "No worries. Are you checking in today? Do you have a reservation?"
    
    # Default: pedir nome
    if not state.slots['name']:
        return "May I have your name, please?"
    elif state.slots['reservation'] is None:
        return f"Thank you, {state.slots['name']}. Do you have a reservation?"
    
    return "How can I help you today?"

def handle_stage_id_payment(state: SimulatorState, intent: SimulatorIntent, text: str) -> str:
    """
    Stage 3: ID and payment
    """
    if intent == SimulatorIntent.PROVIDE_ID:
        state.slots['id_confirmed'] = True
        if state.slots['payment_method']:
            # Já tem pagamento, pode ir para preferências
            state.stage = SimulatorStage.ROOM_PREFERENCES
            return "Thank you. Here's your key card. Would you like a room with a beach view or a city view?"
        else:
            return "Thank you. How would you like to pay — credit card or cash?"
    
    if intent == SimulatorIntent.PROVIDE_PAYMENT:
        payment = extract_slot_value(text, 'payment')
        if payment:
            state.slots['payment_method'] = payment
            if state.slots['id_confirmed']:
                # Já tem ID, pode ir para preferências
                state.stage = SimulatorStage.ROOM_PREFERENCES
                return "Perfect. Here's your key card. Would you like a room with a beach view or a city view?"
            else:
                return "Great. May I see your ID, please?"
        else:
            return "How would you like to pay — credit card or cash?"
    
    if intent == SimulatorIntent.CONFUSION:
        if not state.slots['id_confirmed']:
            return "Could I see your ID or passport, please?"
        elif not state.slots['payment_method']:
            return "How would you like to pay — credit card or cash?"
    
    # Default
    if not state.slots['id_confirmed']:
        return "May I see your ID, please?"
    elif not state.slots['payment_method']:
        return "How would you like to pay — credit card or cash?"
    
    return "Is there anything else I can help you with?"

def handle_stage_room_preferences(state: SimulatorState, intent: SimulatorIntent, text: str) -> str:
    """
    Stage 4: Room preferences
    """
    if intent == SimulatorIntent.REQUEST_VIEW:
        view = extract_slot_value(text, 'view')
        if view:
            state.slots['preferences']['view'] = view
            state.stage = SimulatorStage.INFO_AND_CLOSING
            return f"Perfect — a {view} view room. King bed or two singles?"
        else:
            return "Would you like a beach view or a city view?"
    
    if intent == SimulatorIntent.ASK_ROOM:
        bed = extract_slot_value(text, 'bed')
        if bed:
            state.slots['preferences']['bed'] = bed
            state.stage = SimulatorStage.INFO_AND_CLOSING
            return handle_stage_info_closing(state)
        else:
            return "King bed or two singles?"
    
    if intent == SimulatorIntent.CONFUSION:
        return "Would you like a room with a beach view or a city view?"
    
    # Default
    if not state.slots['preferences']['view']:
        return "Would you like a room with a beach view or a city view?"
    elif not state.slots['preferences']['bed']:
        return "King bed or two singles?"
    
    return "Is there anything else you need?"

def handle_stage_info_closing(state: SimulatorState) -> str:
    """
    Stage 5: Info and closing
    """
    return "Perfect! Checkout is at 11 a.m. Breakfast is from 7 to 10 in the morning. Here is your key card. Room 305. Enjoy your stay!"

def handle_stage_optional_issues(state: SimulatorState, intent: SimulatorIntent, text: str) -> str:
    """
    Stage 6: Optional mini-issues
    """
    if intent == SimulatorIntent.REQUEST_SPECIAL:
        if 'late' in normalize_text(text) and 'checkout' in normalize_text(text):
            return "I can arrange a late checkout until 2 p.m. Is that okay?"
        elif 'breakfast' in normalize_text(text):
            return "Breakfast is from 7 to 10 a.m. in the restaurant on the first floor."
        elif 'wifi' in normalize_text(text) or 'internet' in normalize_text(text):
            return "WiFi is free. The password is 'SUNSET2024'. It's on your key card too."
        else:
            return "I'll note that. Is there anything else?"
    
    return "Is there anything else I can help you with?"

# ============================================================================
# HANDLERS ESPECIAIS
# ============================================================================

def handle_teaching_request(state: SimulatorState) -> str:
    """
    Aluno pediu para ensinar - oferecer trocar de modo
    REGRA: Não quebrar roleplay, mas oferecer opção
    """
    state.flags['user_requested_teaching'] = True
    # Resposta natural do recepcionista, sem quebrar roleplay
    return "I can continue helping you here, or if you'd like, we can switch to Learning mode where I'll teach you step by step. Which do you prefer?"

def handle_rude_unsafe(state: SimulatorState) -> str:
    """
    Aluno disse algo rude/ameaçador - redirecionar gentilmente
    """
    return "Let's keep it friendly 😊 So, do you have a reservation?"

def handle_confusion(state: SimulatorState, stage: SimulatorStage) -> str:
    """
    Aluno está confuso - clarificar de forma natural
    """
    state.flags['user_confused'] = True
    
    if stage == SimulatorStage.GREETING:
        return "No worries. Are you checking in today?"
    elif stage == SimulatorStage.RESERVATION_DETAILS:
        return "Let me help. Do you have a reservation, or would you like to book a room?"
    elif stage == SimulatorStage.ID_AND_PAYMENT:
        return "Could you repeat that, please? I need to see your ID and know how you'd like to pay."
    else:
        return "Sorry, I didn't catch that. Could you say it again?"

def handle_off_topic(state: SimulatorState) -> str:
    """
    Aluno saiu do tópico - redirecionar para o cenário
    """
    if state.stage == SimulatorStage.GREETING:
        return "Welcome! Are you checking in today?"
    elif state.slots['name']:
        return f"Let's focus on your check-in, {state.slots['name']}. Do you have a reservation?"
    else:
        return "Let's get you checked in. May I have your name, please?"

def handle_thanks(state: SimulatorState, stage: SimulatorStage) -> str:
    """
    Aluno agradeceu - responder naturalmente e continuar
    """
    if stage == SimulatorStage.GREETING:
        return "You're welcome. Are you checking in today?"
    elif stage == SimulatorStage.RESERVATION_DETAILS:
        if not state.slots['name']:
            return "You're welcome. May I have your name, please?"
        elif state.slots['reservation'] is None:
            return "You're welcome. Do you have a reservation?"
        else:
            return "You're welcome. Could I see your ID, please?"
    else:
        return "You're welcome. Is there anything else I can help you with?"

# ============================================================================
# ORQUESTRADOR PRINCIPAL
# ============================================================================

def validate_simulator_response(response: str) -> str:
    """
    Valida que a resposta não quebra o roleplay
    Remove frases que indicam modo professor
    """
    forbidden_phrases = [
        "let's practice",
        "now i will teach",
        "what do you think",
        "how about you",
        "i will teach you",
        "vamos praticar",
        "agora vou te ensinar",
        "o que você acha"
    ]
    
    response_lower = response.lower()
    for phrase in forbidden_phrases:
        if phrase in response_lower:
            # Substitui por frase natural do personagem
            if "let's practice" in response_lower or "vamos praticar" in response_lower:
                response = response.replace(phrase, "how can I help you")
            elif "teach" in response_lower or "ensinar" in response_lower:
                response = response.replace(phrase, "I can help you with that")
            elif "what do you think" in response_lower or "how about you" in response_lower:
                response = response.replace(phrase, "is there anything else")
    
    return response

def on_simulator_message(student_text: str, state: SimulatorState, theme: str = "hotel") -> str:
    """
    Processa mensagem do aluno no modo simulador
    REGRA CRÍTICA: Nunca quebrar o roleplay com linguagem de professor
    """
    # Detecta intenção
    intent = detect_simulator_intent(student_text, state.stage, state.slots)
    state.last_user_intent = intent.value
    
    # Handlers especiais (prioridade) - todos validados
    if intent == SimulatorIntent.ASK_FOR_TEACHING:
        response = handle_teaching_request(state)
        return validate_simulator_response(response)
    
    if intent == SimulatorIntent.RUDE_UNSAFE:
        response = handle_rude_unsafe(state)
        return validate_simulator_response(response)
    
    if intent == SimulatorIntent.THANKS:
        response = handle_thanks(state, state.stage)
        return validate_simulator_response(response)
    
    if intent == SimulatorIntent.CONFUSION:
        response = handle_confusion(state, state.stage)
        return validate_simulator_response(response)
    
    if intent == SimulatorIntent.OFF_TOPIC:
        response = handle_off_topic(state)
        return validate_simulator_response(response)
    
    # Handlers por stage
    if state.stage == SimulatorStage.GREETING:
        if intent == SimulatorIntent.GREETING:
            # Primeira mensagem - iniciar simulação
            response = handle_stage_greeting(state, theme)
            if response:
                response = validate_simulator_response(response)
                return response
        # Continuar para reservation
        state.stage = SimulatorStage.RESERVATION_DETAILS
        response = handle_stage_reservation(state, intent, student_text)
        response = validate_simulator_response(response)
        return response
    
    elif state.stage == SimulatorStage.RESERVATION_DETAILS:
        response = handle_stage_reservation(state, intent, student_text)
        # Avançar stage se necessário
        if state.slots['name'] and state.slots['reservation'] is not None:
            state.stage = SimulatorStage.ID_AND_PAYMENT
        return validate_simulator_response(response)
    
    elif state.stage == SimulatorStage.ID_AND_PAYMENT:
        response = handle_stage_id_payment(state, intent, student_text)
        # Avançar stage se necessário
        if state.slots['id_confirmed'] and state.slots['payment_method']:
            state.stage = SimulatorStage.ROOM_PREFERENCES
        return validate_simulator_response(response)
    
    elif state.stage == SimulatorStage.ROOM_PREFERENCES:
        response = handle_stage_room_preferences(state, intent, student_text)
        return validate_simulator_response(response)
    
    elif state.stage == SimulatorStage.INFO_AND_CLOSING:
        if intent == SimulatorIntent.REQUEST_SPECIAL:
            state.stage = SimulatorStage.OPTIONAL_ISSUES
            response = handle_stage_optional_issues(state, intent, student_text)
        else:
            response = "Is there anything else I can help you with?"
        return validate_simulator_response(response)
    
    elif state.stage == SimulatorStage.OPTIONAL_ISSUES:
        response = handle_stage_optional_issues(state, intent, student_text)
        return validate_simulator_response(response)
    
    # Fallback
    response = "How can I help you today?"
    
    # VALIDAÇÃO FINAL: Garantir que resposta não quebra roleplay
    response = validate_simulator_response(response)
    
    return response
