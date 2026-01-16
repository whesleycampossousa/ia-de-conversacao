# 🔊 Como Habilitar o Text-to-Speech (Áudio)

## ⚠️ Problema Atual
A aplicação está configurada para usar o **Google Cloud Text-to-Speech API**, mas você precisa habilitar essa API no seu projeto do Google Cloud.

## 💰 Custos
- **Preço**: ~$4 USD por 1 milhão de caracteres (vozes Neural2)
- **Teste grátis**: Primeiros $300 de crédito grátis no Google Cloud
- **Uso normal**: Muito barato - cada frase custa menos de $0.001

## 📋 Passos para Habilitar

### 1️⃣ Acessar o Console do Google Cloud
```
https://console.cloud.google.com/
```

### 2️⃣ Selecionar ou Criar um Projeto
1. No topo da página, clique no nome do projeto
2. Se não tiver projeto, clique em "Novo Projeto"
3. Nome sugerido: "IA-Conversacao" ou similar

### 3️⃣ Habilitar a API Cloud Text-to-Speech
Acesse diretamente:
```
https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
```

Ou manualmente:
1. Menu lateral → "APIs e Serviços" → "Biblioteca"
2. Busque por "Cloud Text-to-Speech API"
3. Clique em "ATIVAR"

### 4️⃣ Verificar se a API Key tem Permissões
1. Vá em: https://console.cloud.google.com/apis/credentials
2. Encontre sua API Key (a mesma do `.env`)
3. Clique no ícone de editar (lápis)
4. Em "Restrições de API":
   - Se estiver restrito, adicione "Cloud Text-to-Speech API"
   - OU deixe "Nenhuma restrição" (menos seguro, mas mais fácil)
5. Salve

### 5️⃣ Testar a Aplicação
```bash
python api/index.py
```

Acesse: http://localhost:4004

## ✅ O que foi Corrigido no Código

1. ✅ **Mensagens repetidas**: Agora limpa a tela ao clicar em "Iniciar Conversa"
2. ✅ **Configuração TTS**: Usando vozes Neural2 (melhor qualidade)
3. ✅ **Tratamento de erros**: Se o áudio falhar, não bloqueia a conversa

## 🎯 Vozes Disponíveis

A aplicação está usando:
- **Idioma**: Inglês (en-US) - já que a conversa é em inglês
- **Voz**: Neural2-C (feminina, alta qualidade)
- **Alternativas disponíveis**:
  - `en-US-Neural2-A` - Masculina
  - `en-US-Neural2-D` - Masculina
  - `en-US-Neural2-F` - Feminina

Para trocar a voz, edite a linha 486 do arquivo `api/index.py`:
```python
name="en-US-Neural2-C",  # Troque aqui
```

## 🔧 Solução Alternativa: Usar Voz Gratuita

Se não quiser usar a API paga, posso configurar a gTTS (gratuita mas com menos qualidade).

## 📊 Monitorar Uso e Custos

Acompanhe o uso em:
```
https://console.cloud.google.com/billing
```

## ❓ Dúvidas Comuns

**P: A API Key funciona para Gemini mas não para TTS?**
R: Sim, cada API precisa ser habilitada separadamente no projeto.

**P: Vou ser cobrado?**
R: Só após esgotar os $300 de crédito grátis. Depois, é cobrado por uso.

**P: Qual o consumo médio?**
R: Uma conversa de 10 minutos (20 respostas) ≈ 500 caracteres ≈ $0.002 USD

**P: Posso desabilitar o áudio?**
R: Sim, o código já trata isso. Se falhar, apenas não toca o áudio mas continua funcionando.

## 🚀 Pronto!

Após habilitar a API, reinicie o servidor e teste:
1. Inicie o servidor: `python api/index.py`
2. Acesse a aplicação
3. Clique em "Iniciar Conversa"
4. O áudio deve funcionar! 🔊
