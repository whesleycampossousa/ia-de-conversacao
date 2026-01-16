import pandas as pd
import json

# Read Excel file
df = pd.read_excel('sales_aohqw_1768560610634.xlsx')

# Extract unique emails
emails = df['Customer Email'].dropna().unique().tolist()

print(f'Total de emails extraidos: {len(emails)}')
print('\nPrimeiros 5 emails:')
for email in emails[:5]:
    print(f'  - {email}')

# Create authorized emails data
emails_data = {
    'admin': 'everydayconversation1991@gmail.com',
    'authorized_emails': emails
}

# Save to JSON
with open('authorized_emails.json', 'w', encoding='utf-8') as f:
    json.dump(emails_data, f, indent=2, ensure_ascii=False)

print(f'\nArquivo criado: authorized_emails.json')
print(f'Total de emails autorizados: {len(emails)}')
print(f'Email admin: {emails_data["admin"]}')
