#!/usr/bin/env python3
"""
Script to restore authorized emails from Excel file
This script extracts emails from the sales Excel file and creates/updates authorized_emails.json

Usage:
    python restore_authorized_emails.py
"""

import pandas as pd
import json
import os
import sys

def restore_emails():
    """Restore authorized emails from Excel file"""
    excel_file = 'sales_aohqw_1768560610634.xlsx'
    output_file = 'authorized_emails.json'
    
    # Check if Excel file exists
    if not os.path.exists(excel_file):
        print(f"❌ ERROR: Excel file not found: {excel_file}")
        print("Please make sure the sales Excel file is in the current directory.")
        sys.exit(1)
    
    try:
        # Read Excel file
        print(f"📖 Reading Excel file: {excel_file}")
        df = pd.read_excel(excel_file)
        
        # Extract unique emails
        if 'Customer Email' not in df.columns:
            print(f"❌ ERROR: Column 'Customer Email' not found in Excel file")
            print(f"Available columns: {', '.join(df.columns)}")
            sys.exit(1)
        
        emails = df['Customer Email'].dropna().unique().tolist()
        print(f"✅ Extracted {len(emails)} unique emails")
        
        # Create authorized emails data
        admin_email = 'everydayconversation1991@gmail.com'
        emails_data = {
            'admin': admin_email,
            'authorized_emails': emails
        }
        
        # Check if file already exists
        if os.path.exists(output_file):
            print(f"⚠️  File {output_file} already exists")
            response = input("Do you want to overwrite it? (yes/no): ").lower()
            if response not in ['yes', 'y']:
                print("❌ Operation cancelled")
                sys.exit(0)
        
        # Save to JSON
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(emails_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ SUCCESS!")
        print(f"📁 File created: {output_file}")
        print(f"📧 Total authorized emails: {len(emails)}")
        print(f"👤 Admin email: {admin_email}")
        print(f"\nFirst 5 emails:")
        for email in emails[:5]:
            print(f"  - {email}")
        
        if len(emails) > 5:
            print(f"  ... and {len(emails) - 5} more")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    print("=" * 60)
    print("🔧 Restore Authorized Emails Script")
    print("=" * 60)
    print()
    
    restore_emails()
    
    print()
    print("=" * 60)
    print("🎉 Done! You can now start the server.")
    print("=" * 60)
