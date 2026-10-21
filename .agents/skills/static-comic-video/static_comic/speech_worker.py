"""Locked offline WhisperX worker. Stdout is JSON; diagnostics go to stderr."""
from contextlib import redirect_stdout
from io import BytesIO
from pathlib import Path
import sys
import wave

from .contracts import canonical, read_json
from .paths import read_bytes


def run(root, request):
    import numpy as np
    from nltk.tokenize.punkt import PunktSentenceTokenizer
    from unittest.mock import patch
    from whisperx.alignment import align, load_align_model
    from scripts.probe_models import verify_model
    lock = request["lock"]
    if lock["device"] not in ("cpu","cuda"):
        raise ValueError("Unsupported alignment device")
    model_path = verify_model(lock["alignment"])
    model, metadata = load_align_model("zh",lock["device"],model_name=str(model_path),model_cache_only=True)
    data = read_bytes(root,"work/audio/align_16k.wav",512*1024*1024)
    with wave.open(BytesIO(data),"rb") as stream:
        if (stream.getframerate(),stream.getnchannels(),stream.getsampwidth()) != (16000,1,2):
            raise ValueError("Expected 16 kHz mono PCM")
        audio = np.frombuffer(stream.readframes(stream.getnframes()),dtype="<i2").astype(np.float32)/32768
    outputs = []
    for window in request["plan"]["windows"]:
        start,end = window["input_16k"]
        clip = audio[start:end]
        if len(clip) > 30*16000:
            result = {"segments":[],"word_segments":[]}
        else:
            # Our normalized window contains no punctuation or spaces: it is one
            # sentence already. Use NLTK's untrained tokenizer in this isolated
            # worker instead of WhisperX downloading unrelated English Punkt data.
            splitter = PunktSentenceTokenizer()
            if list(splitter.span_tokenize(window["text"])) != [(0,len(window["text"]))]:
                raise ValueError("Expected one normalized alignment sentence")
            with patch("whisperx.alignment.nltk_load", return_value=splitter):
                result = align([{"text":window["text"],"start":0.,"end":len(clip)/16000}],
                               model,metadata,clip,lock["device"],return_char_alignments=True)
        outputs.append({"window":window,"result":result,
                        "dictionary_characters":sorted(c for c in set(window["text"]) if c in metadata["dictionary"])})
    return outputs


if __name__ == "__main__":
    root = Path(sys.argv[1]).resolve(strict=True)
    request = read_json(read_bytes(root,sys.argv[2],32*1024*1024))
    with redirect_stdout(sys.stderr):
        result = run(root,request)
    sys.stdout.buffer.write(canonical(result))
