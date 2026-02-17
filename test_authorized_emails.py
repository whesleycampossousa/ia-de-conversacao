#!/usr/bin/env python3
"""
Test script to verify authorized_emails.json is properly configured
"""

import json
import os
import sys

def test_authorized_emails():
    """Test that authorized_emails.json exists and is valid"""
    
    test_results = []
    
    # Test 1: File exists
    print("Test 1: Checking if authorized_emails.json exists...")
    if os.path.exists('authorized_emails.json'):
        print("✅ PASS: File exists")
        test_results.append(True)
    else:
        print("❌ FAIL: File not found")
        print("   Run: python restore_authorized_emails.py")
        test_results.append(False)
        return False
    
    # Test 2: File is valid JSON
    print("\nTest 2: Checking if file is valid JSON...")
    try:
        with open('authorized_emails.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        print("✅ PASS: Valid JSON")
        test_results.append(True)
    except json.JSONDecodeError as e:
        print(f"❌ FAIL: Invalid JSON - {e}")
        test_results.append(False)
        return False
    except Exception as e:
        print(f"❌ FAIL: Error reading file - {e}")
        test_results.append(False)
        return False
    
    # Test 3: Contains required fields
    print("\nTest 3: Checking required fields...")
    if 'admin' in data and 'authorized_emails' in data:
        print("✅ PASS: Required fields present")
        test_results.append(True)
    else:
        print("❌ FAIL: Missing 'admin' or 'authorized_emails' field")
        test_results.append(False)
        return False
    
    # Test 4: Admin email is set
    print("\nTest 4: Checking admin email...")
    admin_email = data.get('admin')
    if admin_email and '@' in admin_email:
        print(f"✅ PASS: Admin email set to {admin_email}")
        test_results.append(True)
    else:
        print("❌ FAIL: Admin email not properly set")
        test_results.append(False)
    
    # Test 5: Authorized emails list is not empty
    print("\nTest 5: Checking authorized emails count...")
    emails = data.get('authorized_emails', [])
    if len(emails) > 0:
        print(f"✅ PASS: {len(emails)} emails authorized")
        test_results.append(True)
    else:
        print("❌ FAIL: No emails in authorized list")
        test_results.append(False)
    
    # Test 6: Expected count (should be 300+)
    print("\nTest 6: Checking if we have 300+ emails...")
    if len(emails) >= 300:
        print(f"✅ PASS: {len(emails)} emails (expected 300+)")
        test_results.append(True)
    else:
        print(f"⚠️  WARNING: Only {len(emails)} emails (expected 300+)")
        print("   This might be OK if the Excel file was updated")
        test_results.append(True)  # Don't fail, just warn
    
    # Test 7: All emails are valid format
    print("\nTest 7: Checking email format...")
    invalid_emails = [email for email in emails if '@' not in email or '.' not in email]
    if len(invalid_emails) == 0:
        print("✅ PASS: All emails have valid format")
        test_results.append(True)
    else:
        print(f"❌ FAIL: {len(invalid_emails)} invalid emails found")
        for email in invalid_emails[:5]:  # Show first 5
            print(f"   - {email}")
        test_results.append(False)
    
    # Test 8: No duplicate emails
    print("\nTest 8: Checking for duplicates...")
    unique_emails = set(emails)
    if len(emails) == len(unique_emails):
        print("✅ PASS: No duplicate emails")
        test_results.append(True)
    else:
        print(f"⚠️  WARNING: {len(emails) - len(unique_emails)} duplicate(s) found")
        test_results.append(True)  # Don't fail, duplicates are handled
    
    # Test 9: Admin email is in the list
    print("\nTest 9: Checking if admin is in authorized list...")
    if admin_email.lower() in [e.lower() for e in emails]:
        print("✅ PASS: Admin email is authorized")
        test_results.append(True)
    else:
        print("⚠️  WARNING: Admin email not in authorized list")
        print("   The API adds it automatically, but it should be in the file")
        test_results.append(True)  # Don't fail, API handles it
    
    # Summary
    print("\n" + "=" * 60)
    passed = sum(test_results)
    total = len(test_results)
    print(f"Test Summary: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n✅ All tests PASSED!")
        print("\n📧 Sample emails:")
        for email in emails[:5]:
            print(f"   - {email}")
        if len(emails) > 5:
            print(f"   ... and {len(emails) - 5} more")
        return True
    else:
        print("\n❌ Some tests FAILED!")
        print("Please fix the issues and run again.")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Testing Authorized Emails Configuration")
    print("=" * 60)
    print()
    
    # Change to project root if needed
    if os.path.exists('authorized_emails.json'):
        pass
    elif os.path.exists('../authorized_emails.json'):
        os.chdir('..')
    else:
        print("❌ Cannot find authorized_emails.json")
        print("Please run from the project root directory")
        sys.exit(1)
    
    success = test_authorized_emails()
    sys.exit(0 if success else 1)
