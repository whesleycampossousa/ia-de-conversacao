import asyncio
import json
import os
from pathlib import Path
import edge_tts

# --- Configuration ---
VOICE = "en-US-EricNeural"  # The requested "Eric" voice
SCENARIO_FILE = "../scenario.json"
OUTPUT_DIR = "../assets/audio"

async def generate_audio(text, output_path):
    print(f"Generating: {output_path}...")
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(output_path)
    print("Success.")

async def main():
    # Setup paths
    base_dir = Path(__file__).parent
    scenario_path = base_dir / SCENARIO_FILE
    output_dir = base_dir / OUTPUT_DIR
    
    # Ensure output dir exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load Scenario
    if not scenario_path.exists():
        print(f"Error: Scenario file not found at {scenario_path}")
        return

    with open(scenario_path, 'r', encoding='utf-8') as f:
        scenario = json.load(f)

    # Process
    for step in scenario:
        filename = step["audio_file"]
        text = step["text"]
        output_path = output_dir / filename
        
        # We can uncomment this if we want to skip existing files, 
        # but for now let's overwrite to ensure we have the correct voice.
        # if output_path.exists():
        #     print(f"Skipping {filename} (already exists)")
        #     continue
            
        await generate_audio(text, str(output_path))

if __name__ == "__main__":
    asyncio.run(main())
