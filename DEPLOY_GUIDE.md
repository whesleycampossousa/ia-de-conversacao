# 🚀 Início Rápido - Deploy para Produção

Este guia resume os passos para colocar sua aplicação de IA de conversação em produção.

## ✅ Já Configurado

- ✓ SESSION_SECRET gerado automaticamente
- ✓ Arquivo `.env` atualizado
- ✓ Scripts de setup criados

## 📋 Próximos Passos (Você Precisa Fazer)

### 1️⃣ Obter API Key do Gemini

**Execute o script:**
```bash
obter_api_key.bat
```

Ou acesse manualmente: https://aistudio.google.com/app/apikey

**Depois:**
1. Faça login com sua conta Google
2. Clique em "Create API Key"
3. Copie a chave
4. Abra o arquivo `.env`
5. Substitua `your_api_key_here` pela sua chave

### 2️⃣ Testar Localmente

**Execute:**
```bash
setup.bat
```

Este script vai:
- Verificar dependências
- Instalar requirements
- Validar configuração
- Mostrar como iniciar o servidor

**Ou manualmente:**
```bash
pip install -r requirements.txt
python api/index.py
```

Acesse: http://localhost:4004

### 3️⃣ Deploy no Vercel

**Via CLI:**
```bash
# Instalar Vercel CLI (primeira vez)
npm i -g vercel

# Login
vercel login

# Configurar variáveis de ambiente
vercel env add GOOGLE_API_KEY
vercel env add SESSION_SECRET
vercel env add ALLOWED_ORIGINS
vercel env add RATE_LIMIT_REQUESTS
vercel env add RATE_LIMIT_WINDOW

# Deploy
vercel --prod
```

**Valores das variáveis:**
- `GOOGLE_API_KEY`: Sua chave do Gemini
- `SESSION_SECRET`: `bed48c5f0f5d6fea2adc7da413b0f798c10c6de0218e16d7e9ca5a65b4bccace`
- `ALLOWED_ORIGINS`: `https://seu-app.vercel.app` (atualizar após primeiro deploy)
- `RATE_LIMIT_REQUESTS`: `30`
- `RATE_LIMIT_WINDOW`: `60`

## 📚 Documentação Completa

Para instruções detalhadas, consulte:
- **[Guia Completo de Deploy](file:///.gemini/antigravity/brain/0a38f8db-df28-470a-bd29-6e8748eba35a/implementation_plan.md)** - Passo a passo detalhado
- **[Task Checklist](file:///.gemini/antigravity/brain/0a38f8db-df28-470a-bd29-6e8748eba35a/task.md)** - Progresso das tarefas

## 🆘 Precisa de Ajuda?

- **Erro de API Key**: Verifique se configurou corretamente no `.env`
- **Erro de CORS**: Atualize `ALLOWED_ORIGINS` no Vercel
- **Outros problemas**: Consulte a seção Troubleshooting no guia completo

---

**Resumo Visual dos Passos:**

```
┌─────────────────────────────────────┐
│ 1. obter_api_key.bat                │
│    ↓                                 │
│ 2. Editar .env                      │
│    ↓                                 │
│ 3. setup.bat (testar local)         │
│    ↓                                 │
│ 4. vercel --prod (deploy)           │
└─────────────────────────────────────┘
```

🎯 **Seu objetivo**: Executar esses 4 passos e sua aplicação estará no ar!
