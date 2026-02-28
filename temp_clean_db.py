import json
import re

SCENARIOS_PATH = r'c:\Users\whesl\OneDrive\Documentos\Projetos\_Projetos_Ativos\IA de conversação\scenarios_db.json'

def clean_simulator_prompt(text):
    if not text: return ""
    # Remove "MANDATORY OPENING" rules as they are handled by the API override
    text = re.sub(r'MANDATORY OPENING:.*?\n?', '', text)
    # Remove repeated "CRITICAL: Be more natural" lines
    text = re.sub(r'CRITICAL: Be more natural\. Do NOT act like an AI\.', '', text)
    # Remove redundant FORBIDDEN PHRASES if they are just the standard ones
    text = re.sub(r'FORBIDDEN PHRASES: Do NOT use \'What do you think\?\', \'How about you\?\', \'Does that make sense\?\'\.', '', text)
    # Trim and clean whitespace
    text = text.strip()
    return text

def main():
    # Since I overwrote the file with a truncated version in the last tool call,
    # I should ideally have used a backup. But I have the contents in my history.
    # I will reconstruct it with a few representative ones first, then I'll ask the user
    # or use my previous view_file content. 
    # Actually, I can just use the content I saw in Step 1368.
    
    # FOR SAFETY: I will fetch the most complete version I had recently.
    pass

if __name__ == "__main__":
    main()
