# Mistral STT Status

This document is kept as an archive note. The original Mistral provider work is already implemented in the main codebase:

- `src/dicton/stt_mistral.py`
- `src/dicton/stt_factory.py`
- `tests/test_stt_mistral.py`

Current status:

- Mistral is a supported STT provider.
- The default provider fallback order prefers Mistral, then ElevenLabs.
- Mistral support is covered by unit tests.

Follow-up work, if needed later:

- Add live integration coverage with real Mistral credentials.
- Add retry/backoff policy if API behavior warrants it.
- Add richer UI controls only if the configuration dashboard needs them.
- [ ] Test config loading

### 4.3 Manual Validation

- [ ] Test with real Mistral API key
- [ ] Verify transcription accuracy on sample audio
- [ ] Compare latency vs ElevenLabs
- [ ] Verify cost (check Mistral dashboard usage)
- [ ] Test with different languages (EN, FR, DE, ES)

---

## Phase 5: Documentation

### 5.1 User Documentation

- [ ] Update README.md with Mistral option
- [ ] Document API key setup process
- [ ] Document when to choose Mistral vs other providers
- [ ] Add cost comparison section

### 5.2 Code Documentation

- [ ] Docstrings for `MistralSTTProvider` class
- [ ] Docstrings for all public methods
- [ ] Type hints for all parameters

---

## Implementation Notes

### Mistral API Quick Reference

```python
from mistralai import Mistral
import os

# Initialize client
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

# Transcribe audio
result = client.audio.transcriptions.complete(
    model="voxtral-mini-latest",
    file={"content": wav_buffer, "file_name": "audio.wav"},
    # language="en",  # Optional: boost accuracy (incompatible with timestamps)
    # timestamp_granularities=["segment"]  # Optional: get timing info
)

# Access result
text = result.text
language = result.language  # Detected language
# segments = result.segments  # If timestamps requested
```

### Key Constraints

1. **No streaming**: Mistral only supports batch transcription
2. **Duration limit**: ~15 minutes max per request
3. **Timestamp/language conflict**: Cannot use both parameters together
4. **Languages**: Best for EN, FR, DE, ES, PT, HI, NL, IT

### Cost Calculation

| Usage | ElevenLabs | Mistral | Savings |
|-------|------------|---------|---------|
| 1 hour/day | $12/mo | $1.80/mo | 85% |
| 10 hours/day | $120/mo | $18/mo | 85% |

---

## Acceptance Criteria

- [ ] `STT_PROVIDER=mistral` enables Mistral transcription
- [ ] Transcription accuracy comparable to ElevenLabs on major languages
- [ ] Fallback to next provider on Mistral API errors
- [ ] Configuration visible in dashboard
- [ ] API key securely stored in `.env`
- [ ] All tests pass
- [ ] No regression in existing ElevenLabs/Gladia functionality

---

## References

| Resource | URL |
|----------|-----|
| Mistral Audio Transcription | https://docs.mistral.ai/capabilities/audio_transcription |
| Mistral Python SDK | https://github.com/mistralai/client-python |
| Mistral Pricing | https://mistral.ai/products/la-plateforme#pricing |
| Voxtral Announcement | https://mistral.ai/news/voxtral |

---

## Version Tracking

- **Target Version**: v1.x.0 (minor bump on completion)
- **Branch**: `feat/mistral-stt-provider`
- **Estimated Effort**: 2-3 development sessions

---

## Agent Instructions

When working on this feature:
1. Check off completed items with `[x]`
2. Follow commit convention: `feat:`, `fix:`, `chore:`, `test:`
3. Reference this file in commit messages when relevant
4. Run tests before marking tasks complete
5. After completing all phases → merge to main, tag release
