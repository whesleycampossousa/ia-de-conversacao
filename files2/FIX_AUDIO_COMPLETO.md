# 🔊 GUIA COMPLETO - CORRIGIR ÁUDIO

## 🎯 PROBLEMA: Áudio não funciona (nem transcrição nem TTS)

Existem 2 sistemas de áudio:
1. **Transcrição** (você fala → texto) - Usa Groq Whisper
2. **Text-to-Speech** (texto → IA fala) - Usa Google Cloud TTS

---

## ✅ SOLUÇÃO RÁPIDA (Recomendada)

### Passo 1: Adicionar GROQ_API_KEY no .env

Abra o arquivo `.env` na raiz do projeto e adicione:

```env
# Existing keys
GOOGLE_API_KEY=sua_chave_aqui

# ADD THIS LINE:
GROQ_API_KEY=sua_chave_groq_aqui
```

**Como obter a chave Groq:**
1. Acesse: https://console.groq.com/keys
2. Faça login (pode usar Google)
3. Clique em "Create API Key"
4. Copie a chave
5. Cole no .env

### Passo 2: Habilitar Google Cloud Text-to-Speech

A chave do Gemini (GOOGLE_API_KEY) também serve para TTS, mas você precisa **habilitar a API**:

1. Acesse: https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
2. Faça login com a mesma conta do Gemini
3. Clique em **"ATIVAR"** (ENABLE)
4. Aguarde 1-2 minutos

### Passo 3: Reiniciar o Servidor

```bash
# Pare o servidor (Ctrl+C)
# Inicie novamente:
python api/index.py
```

Você deve ver:
```
[OK] Groq API key configured for speech-to-text
[OK] Gemini model initialized successfully
```

### Passo 4: Testar no Navegador

1. Acesse http://localhost:4004
2. Faça login
3. Escolha um cenário
4. Clique em "Iniciar Conversa"
5. Clique no ícone do microfone 🎤
6. Permita o acesso ao microfone quando o navegador pedir
7. Fale algo em inglês
8. Deve aparecer sua fala transcrita e a IA deve responder com áudio

---

## 🔍 DIAGNÓSTICO: Por que não está funcionando?

Execute este comando no terminal:

```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('GOOGLE_API_KEY:', 'CONFIGURADA' if os.getenv('GOOGLE_API_KEY') else 'FALTANDO'); print('GROQ_API_KEY:', 'CONFIGURADA' if os.getenv('GROQ_API_KEY') else 'FALTANDO')"
```

**Resultado esperado:**
```
GOOGLE_API_KEY: CONFIGURADA
GROQ_API_KEY: CONFIGURADA
```

Se aparecer "FALTANDO", você precisa adicionar a chave no `.env`.

---

## 🛠️ SOLUÇÃO ALTERNATIVA (Se não quiser usar Groq)

### Usar apenas input de texto (sem microfone)

O app tem um fallback automático. Se o áudio não funcionar:
1. Um campo de texto aparece automaticamente
2. Digite sua mensagem em vez de falar
3. A IA ainda responderá (mas sem áudio)

### Desabilitar TTS mas manter transcrição

No arquivo `api/index.py`, procure por:

```python
@app.route('/api/tts', methods=['POST'])
```

Comente a função inteira ou retorne vazio:
```python
@app.route('/api/tts', methods=['POST'])
def tts():
    # Retornar áudio vazio
    return jsonify({"error": "TTS disabled"}), 503
```

---

## 📋 CHECKLIST COMPLETO

### Para Transcrição Funcionar:
- [ ] GROQ_API_KEY configurada no .env
- [ ] Navegador tem permissão para acessar o microfone
- [ ] Navegador é Chrome ou Edge (Firefox/Safari têm suporte limitado)
- [ ] Servidor reiniciado após adicionar a chave

### Para Text-to-Speech Funcionar:
- [ ] GOOGLE_API_KEY configurada no .env
- [ ] Google Cloud Text-to-Speech API habilitada no console
- [ ] Servidor reiniciado após habilitar
- [ ] Sem bloqueador de áudio no navegador

---

## 🆘 PROBLEMAS COMUNS

### ❌ "Transcription service not configured"
**Solução:** Adicione GROQ_API_KEY no .env

### ❌ "Text-to-speech temporarily unavailable"
**Solução:** Habilite a API no console do Google Cloud

### ❌ Microfone não funciona
**Solução:** 
1. Verifique permissões do navegador (ícone de cadeado na barra de endereço)
2. Use Chrome ou Edge
3. Teste o microfone em outro site (ex: online-voice-recorder.com)

### ❌ "Could not transcribe audio - no speech detected"
**Solução:**
1. Fale mais alto e mais devagar
2. Verifique se o microfone correto está selecionado
3. Teste com frases mais longas (mínimo 3 palavras)

---

## 💰 CUSTOS

### Groq Whisper (Transcrição)
- **GRÁTIS** até 14.400 minutos/mês
- Depois: ~$0.111 por hora de áudio

### Google Cloud TTS (Áudio da IA)
- **$300 grátis** para novos usuários
- Vozes Neural2: ~$16 por 1 milhão de caracteres
- Uso normal: ~$0.002 por conversa de 10 minutos

**Resumo:** É praticamente grátis para uso pessoal!

---

## 🎬 EXEMPLO DE .env COMPLETO

```env
# Google Gemini & TTS
GOOGLE_API_KEY=AIzaSyD-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Groq Whisper (Transcrição)
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Outras configurações
SESSION_SECRET=bed48c5f0f5d6fea2adc7da413b0f798c10c6de0218e16d7e9ca5a65b4bccace
ALLOWED_ORIGINS=http://localhost:4004
RATE_LIMIT_REQUESTS=30
RATE_LIMIT_WINDOW=60
```

---

## 🚀 SCRIPT DE TESTE RÁPIDO

Salve este código como `testar_audio.py` na raiz do projeto:

```python
import os
from dotenv import load_dotenv

load_dotenv()

print("="*60)
print("   TESTE DE CONFIGURAÇÃO DE ÁUDIO")
print("="*60)

# Testar Groq
groq_key = os.getenv("GROQ_API_KEY")
if groq_key:
    print("✅ GROQ_API_KEY: Configurada")
    print(f"   Primeiros caracteres: {groq_key[:15]}...")
else:
    print("❌ GROQ_API_KEY: FALTANDO")
    print("   Adicione no .env: GROQ_API_KEY=sua_chave")

print()

# Testar Google
google_key = os.getenv("GOOGLE_API_KEY")
if google_key:
    print("✅ GOOGLE_API_KEY: Configurada")
    print(f"   Primeiros caracteres: {google_key[:15]}...")
else:
    print("❌ GOOGLE_API_KEY: FALTANDO")
    print("   Adicione no .env: GOOGLE_API_KEY=sua_chave")

print()
print("="*60)

if groq_key and google_key:
    print("✅ CONFIGURAÇÃO OK - Áudio deve funcionar!")
else:
    print("❌ CONFIGURAÇÃO INCOMPLETA - Siga as instruções acima")

print("="*60)
```

Execute:
```bash
python testar_audio.py
```

---

## 📞 RESUMO ULTRA-RÁPIDO

1. **Obtenha chave Groq:** https://console.groq.com/keys
2. **Adicione no .env:**
   ```
   GROQ_API_KEY=sua_chave_aqui
   ```
3. **Habilite TTS:** https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
4. **Reinicie:** `python api/index.py`
5. **Teste:** http://localhost:4004

**Pronto! 🎉**
