# 🔧 Como Restaurar os Emails Autorizados

## Problema

Se você está vendo a mensagem "Email not authorized" ao tentar fazer login, significa que o arquivo `authorized_emails.json` está faltando ou está vazio.

## Solução Rápida

### 1. Execute o script de restauração

```bash
python restore_authorized_emails.py
```

ou use o script original:

```bash
python extract_emails.py
```

### 2. Verifique que o arquivo foi criado

```bash
ls -lh authorized_emails.json
```

Você deve ver um arquivo de aproximadamente 11KB.

### 3. Reinicie o servidor

```bash
python api/index.py
```

## O que o script faz?

O script `restore_authorized_emails.py`:
1. Lê o arquivo `sales_aohqw_1768560610634.xlsx` (contém os dados dos clientes)
2. Extrai 300+ emails únicos da coluna "Customer Email"
3. Cria o arquivo `authorized_emails.json` no formato correto
4. Inclui o email admin: `everydayconversation1991@gmail.com`

## Estrutura do arquivo gerado

```json
{
  "admin": "everydayconversation1991@gmail.com",
  "authorized_emails": [
    "email1@example.com",
    "email2@example.com",
    ...
  ]
}
```

## ⚠️ IMPORTANTE

- O arquivo `authorized_emails.json` **NÃO** é versionado no Git (está no `.gitignore`)
- Isso é por questões de privacidade dos clientes
- Você precisa gerar este arquivo **localmente** após clonar o repositório
- Em produção, faça upload manual ou use variáveis de ambiente

## Verificação

Para verificar quantos emails foram carregados:

```bash
python -c "import json; data = json.load(open('authorized_emails.json')); print(f'Total: {len(data[\"authorized_emails\"])} emails')"
```

## Pré-requisitos

Você precisa ter instalado:

```bash
pip install pandas openpyxl
```

Ou instale todas as dependências:

```bash
pip install -r requirements.txt
```

## Troubleshooting

### Erro: "Excel file not found"
**Solução**: Certifique-se de que o arquivo `sales_aohqw_1768560610634.xlsx` está no diretório raiz do projeto.

### Erro: "Column 'Customer Email' not found"
**Solução**: O arquivo Excel pode ter sido modificado. Verifique que a coluna com os emails dos clientes existe.

### Ainda não funciona?
Execute o script com mensagens detalhadas:

```bash
python restore_authorized_emails.py
```

O script mostrará:
- ✅ Quantos emails foram extraídos
- 👤 O email admin configurado
- 📧 Primeiros 5 emails da lista

## Deploy em Produção

Para produção (Vercel, etc.), você tem algumas opções:

1. **Upload manual**: Faça upload do arquivo via FTP/SFTP
2. **Endpoint admin**: Crie um endpoint protegido para fazer upload da lista
3. **Banco de dados**: Migre para um banco de dados (PostgreSQL, MongoDB)
4. **Variável de ambiente**: Armazene a lista como JSON em uma variável de ambiente (não recomendado para muitos emails)

## Suporte

Se você continuar tendo problemas, verifique:
1. O arquivo Excel existe?
2. As dependências estão instaladas?
3. O servidor está rodando?
4. Os logs do servidor mostram algum erro?

---

**Nota**: Este processo restaura os 300+ emails que foram acidentalmente removidos. O arquivo é essencial para o funcionamento do sistema de autenticação.
