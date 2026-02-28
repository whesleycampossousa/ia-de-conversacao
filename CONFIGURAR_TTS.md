# 🔊 Configuração do Text-to-Speech

## ✅ Status Atual

Sua `GOOGLE_API_KEY` já está configurada no arquivo `.env`!

## ⚠️ Próximo Passo: Habilitar a API

A chave está configurada, mas você precisa **habilitar a API do Google Cloud Text-to-Speech** no console do Google Cloud.

### Passos Rápidos:

1. **Acesse o link direto:**
   ```
   https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
   ```

2. **Faça login** com a mesma conta Google que você usou para obter a API key do Gemini

3. **Clique em "ATIVAR" ou "ENABLE"**

4. **Aguarde 1-2 minutos** para a API ser ativada

5. **Reinicie o servidor Flask:**
   ```bash
   # Pare o servidor (Ctrl+C)
   # Inicie novamente:
   python api/index.py
   ```

## 🧪 Testar se Funcionou

Após habilitar a API e reiniciar o servidor:

1. Acesse: http://localhost:8912
2. Faça login
3. Escolha um tópico gramatical
4. Selecione uma voz (Sarah, Emma ou James)
5. Clique em "Play"
6. O professor deve falar automaticamente!

## 📋 Verificação Rápida

Execute o script de verificação:
```bash
python configurar_tts.py
```

Ou use o arquivo batch:
```bash
configurar_tts.bat
```

## 🔑 Suas Chaves Configuradas

- ✅ `GOOGLE_API_KEY`: Configurada
- ✅ `GROQ_API_KEY`: Configurada (para transcrição de voz)

## ❓ Problemas?

### Erro 503: Service Unavailable
- **Causa**: API do Text-to-Speech não habilitada
- **Solução**: Siga os passos acima para habilitar a API

### Erro 403: Forbidden
- **Causa**: API key sem permissões
- **Solução**: 
  1. Acesse: https://console.cloud.google.com/apis/credentials
  2. Encontre sua API key
  3. Clique em editar
  4. Em "Restrições de API", adicione "Cloud Text-to-Speech API"
  5. Ou deixe "Nenhuma restrição" (menos seguro, mas mais fácil)

### Não ouve nada
- Verifique se o volume do navegador está ligado
- Verifique se o servidor Flask está rodando
- Abra o console do navegador (F12) e veja se há erros

## 💰 Custos

- **$300 grátis** para novos usuários do Google Cloud
- **Chirp 3 HD** (atual): ~$30 por 1 milhão de caracteres
- Free tier: 1M chars/mês grátis
- Uso normal: ~$0.00006 por conversa de 10 minutos
- 100 alunos × 40 min/semana: ~$150/mês (~R$900)
- **~R$6-9 por aluno/mês**
