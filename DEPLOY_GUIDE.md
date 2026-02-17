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

### 2️⃣ Configurar Emails Autorizados

**IMPORTANTE**: O sistema usa uma lista de emails autorizados (whitelist) para controlar o acesso.

**Para configurar:**
1. Certifique-se de que o arquivo `sales_aohqw_1768560610634.xlsx` está presente (contém os emails dos clientes)
2. Execute o script de extração:
```bash
pip install pandas openpyxl
python extract_emails.py
```

Este script irá:
- Ler o arquivo Excel com os dados dos clientes
- Extrair todos os emails únicos
- Criar o arquivo `authorized_emails.json` com 300+ emails autorizados

**Nota**: O arquivo `authorized_emails.json` não é versionado (está no .gitignore) por questões de privacidade. Você precisa gerá-lo localmente e, se necessário, fazer o upload manual para o servidor de produção.

### 3️⃣ Testar Localmente

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

### 4️⃣ Deploy no Vercel

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

**⚠️ IMPORTANTE - Arquivo authorized_emails.json em Produção:**
Como o arquivo `authorized_emails.json` não é versionado, você precisa enviá-lo manualmente para o Vercel:
1. Após o primeiro deploy, use um método seguro para copiar o arquivo para o servidor
2. Ou configure um endpoint admin para fazer upload do arquivo
3. **Alternativa**: Considere migrar para um banco de dados para gerenciar os emails autorizados em produção

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
│ 3. python extract_emails.py         │
│    ↓                                 │
│ 4. setup.bat (testar local)         │
│    ↓                                 │
│ 5. vercel --prod (deploy)           │
└─────────────────────────────────────┘
```

🎯 **Seu objetivo**: Executar esses 5 passos e sua aplicação estará no ar!
