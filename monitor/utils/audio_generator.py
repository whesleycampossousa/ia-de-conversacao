"""
Audio generator for creating synthetic test audio files
"""
import os
import wave
import struct
import math
from pathlib import Path
from typing import Optional


class AudioGenerator:
    """Generate synthetic WAV audio files for testing"""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate

    def generate_tone(self, frequency: float, duration: float, amplitude: float = 0.5) -> bytes:
        """Generate a sine wave tone"""
        num_samples = int(self.sample_rate * duration)
        samples = []

        for i in range(num_samples):
            t = i / self.sample_rate
            sample = amplitude * math.sin(2 * math.pi * frequency * t)
            # Convert to 16-bit PCM
            sample_int = int(sample * 32767)
            samples.append(struct.pack('<h', sample_int))

        return b''.join(samples)

    def generate_speech_like(self, duration: float = 2.0) -> bytes:
        """Generate speech-like audio (multiple frequencies)"""
        # Human speech fundamental frequencies typically 85-255 Hz
        frequencies = [120, 240, 360, 480]  # Fundamental + harmonics
        amplitudes = [0.5, 0.3, 0.2, 0.1]

        num_samples = int(self.sample_rate * duration)
        samples = []

        for i in range(num_samples):
            t = i / self.sample_rate
            sample = 0

            for freq, amp in zip(frequencies, amplitudes):
                sample += amp * math.sin(2 * math.pi * freq * t)

            # Normalize
            sample = sample / len(frequencies)

            # Add some variation (simulating speech dynamics)
            envelope = math.sin(math.pi * t / duration)  # Fade in/out
            sample = sample * envelope

            # Convert to 16-bit PCM
            sample_int = int(sample * 32767)
            samples.append(struct.pack('<h', sample_int))

        return b''.join(samples)

    def create_wav_file(self, output_path: str, audio_data: bytes) -> bool:
        """Create a WAV file from audio data"""
        try:
            with wave.open(output_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_data)
            return True
        except Exception as e:
            print(f"Error creating WAV file: {e}")
            return False

    def generate_test_audio(self, output_path: str, duration: float = 2.0,
                           audio_type: str = "speech") -> bool:
        """Generate a test audio file"""
        if audio_type == "speech":
            audio_data = self.generate_speech_like(duration)
        elif audio_type == "tone":
            audio_data = self.generate_tone(440, duration)  # A4 note
        else:
            audio_data = self.generate_speech_like(duration)

        return self.create_wav_file(output_path, audio_data)

    def generate_samples(self, output_dir: str, count: int = 10) -> list:
        """Generate multiple test audio samples"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        generated_files = []

        # Generate English samples
        for i in range(count // 2):
            filename = f"en_test_sample_{i+1:02d}.wav"
            filepath = output_path / filename
            duration = 1.5 + (i * 0.3)  # Vary duration
            if self.generate_test_audio(str(filepath), duration, "speech"):
                generated_files.append(str(filepath))

        # Generate Portuguese samples
        for i in range(count // 2):
            filename = f"pt_test_sample_{i+1:02d}.wav"
            filepath = output_path / filename
            duration = 1.8 + (i * 0.3)  # Vary duration
            if self.generate_test_audio(str(filepath), duration, "speech"):
                generated_files.append(str(filepath))

        return generated_files


def generate_all_samples(base_dir: Optional[str] = None):
    """Generate all test audio samples"""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent / "audio_samples"
    else:
        base_dir = Path(base_dir)

    generator = AudioGenerator()

    print("Generating test audio samples...")
    samples = generator.generate_samples(str(base_dir), count=10)

    print(f"Generated {len(samples)} audio samples in {base_dir}")
    for sample in samples:
        print(f"  - {Path(sample).name}")

    return samples


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--generate-samples":
        generate_all_samples()
    else:
        print("Usage: python audio_generator.py --generate-samples")
