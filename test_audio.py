#!/usr/bin/env python3
"""Test script to verify audio setup and Whisper model"""
import sys
import pyaudio
import numpy as np

def test_audio():
    """Test audio input"""
    print("Testing audio input...")

    try:
        audio = pyaudio.PyAudio()

        # List audio devices
        print("\nAvailable audio input devices:")
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  [{i}] {info['name']} - {info['maxInputChannels']} channels")

        # Test recording
        print("\nTesting microphone (speak for 3 seconds)...")
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )

        frames = []
        for _ in range(int(16000 / 1024 * 3)):
            data = stream.read(1024)
            frames.append(data)

            # Show audio level
            audio_data = np.frombuffer(data, dtype=np.int16)
            level = np.max(np.abs(audio_data))
            bars = "=" * min(50, level // 100)
            print(f"\rAudio level: [{bars:<50}]", end="")

        print("\n✓ Audio recording successful!")

        stream.stop_stream()
        stream.close()
        audio.terminate()

        return True

    except Exception as e:
        print(f"✗ Audio test failed: {e}")
        return False

def test_whisper():
    """Test Whisper model loading"""
    print("\nTesting Whisper model...")

    try:
        import whisper
        print("Loading Whisper base model (this may take a moment)...")
        model = whisper.load_model("base")
        print("✓ Whisper model loaded successfully!")

        # Test with dummy audio
        dummy_audio = np.zeros(16000, dtype=np.float32)
        result = model.transcribe(dummy_audio, fp16=False)
        print("✓ Whisper transcription test successful!")

        return True

    except Exception as e:
        print(f"✗ Whisper test failed: {e}")
        return False

def main():
    print("="*60)
    print("Push-to-Write Audio & Model Test")
    print("="*60)

    audio_ok = test_audio()
    whisper_ok = test_whisper()

    print("\n" + "="*60)
    print("Test Results:")
    print(f"  Audio Input: {'✓ PASS' if audio_ok else '✗ FAIL'}")
    print(f"  Whisper Model: {'✓ PASS' if whisper_ok else '✗ FAIL'}")
    print("="*60)

    if audio_ok and whisper_ok:
        print("\n✓ All tests passed! Push-to-Write is ready to use.")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())