#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lesson Spec Builder - Converte grammar_topics.json em LessonSpec
"""

from typing import Dict
from conversation_orchestrator import LessonSpec, MicroGoal, LanguageMode

def build_lesson_spec_from_topic(topic_data: Dict, language_mode: str = 'bilingual') -> LessonSpec:
    """
    Converte um tópico do grammar_topics.json em LessonSpec
    """
    topic_id = topic_data.get('id', '')
    title = topic_data.get('title', '')
    
    # Determina micro_goals baseado no tópico
    micro_goals = []
    
    # Para verb_to_be, cria micro_goals específicos
    if topic_id == 'verb_to_be':
        micro_goals = [
            {
                'id': 'to_be_i_am',
                'explanation_pt': "Use 'I am' para falar de como VOCÊ está.",
                'rule_pt': "I am + adjective.",
                'examples': [
                    {'en': 'I am happy.', 'pt': 'Eu estou feliz.'},
                    {'en': 'I am tired.', 'pt': 'Eu estou cansado(a).'}
                ],
                'practice_prompts': [
                    {'pt': 'Como você está hoje?', 'target_en_hint': 'I am ___.'},
                    {'pt': "Diga: 'Estou cansado(a)'.", 'target_en': 'I am tired.'}
                ],
                'common_errors': [
                    {'pattern': 'I happy', 'fix': 'I am happy', 'tip_pt': "Falta o 'am'."}
                ]
            },
            {
                'id': 'to_be_you_are',
                'explanation_pt': "Use 'You are' para falar de como OUTRA PESSOA está.",
                'rule_pt': "You are + adjective.",
                'examples': [
                    {'en': 'You are happy.', 'pt': 'Você está feliz.'},
                    {'en': 'You are tired.', 'pt': 'Você está cansado(a).'}
                ],
                'practice_prompts': [
                    {'pt': 'Como está seu amigo hoje?', 'target_en_hint': 'You are ___.'},
                ],
                'common_errors': [
                    {'pattern': 'You happy', 'fix': 'You are happy', 'tip_pt': "Falta o 'are'."}
                ]
            }
        ]
    else:
        # Para outros tópicos, cria um micro_goal genérico
        micro_goals = [
            {
                'id': f'{topic_id}_basic',
                'explanation_pt': f"Vamos praticar {title}.",
                'rule_pt': topic_data.get('description', ''),
                'examples': [],
                'practice_prompts': [
                    {'pt': f'Vamos praticar {title}.', 'target_en_hint': 'Try using it in a sentence.'}
                ],
                'common_errors': []
            }
        ]
    
    # Cria LessonSpec
    lesson_spec_data = {
        'topic_id': topic_id,
        'title_pt': title,
        'level': 'beginner',  # Pode ser extraído do tópico se houver
        'language_mode': language_mode,
        'micro_goals': micro_goals,
        'constraints': {
            'max_lines_before_question': 4,
            'allow_portuguese_correction': False,
            'correction_style': 'minimal',
            'end_turn_must_ask_question': True
        }
    }
    
    return LessonSpec(lesson_spec_data)

def get_or_create_session_state(user_id: str, session_states: Dict):
    """
    Obtém ou cria SessionState para um usuário
    """
    if user_id not in session_states:
        from conversation_orchestrator import SessionState
        session_states[user_id] = SessionState()
    return session_states[user_id]
