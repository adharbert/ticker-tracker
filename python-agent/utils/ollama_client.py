import os, json, logging, time
import httpx

log = logging.getLogger(__name__)
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE, timeout: int = 120):
        self.base_url = base_url
        self.timeout  = timeout

    def generate(self, model: str, system: str, prompt: str,
                 retries: int = 3) -> str:
        payload = {
            "model":   model,
            "system":  system,
            "prompt":  prompt,
            "stream":  False,
            "options": {"temperature": 0.1},
        }
        for attempt in range(retries):
            try:
                resp = httpx.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json()["response"].strip()
            except httpx.ConnectError as e:
                if attempt == retries - 1:
                    raise RuntimeError(
                        f"Ollama unreachable at {self.base_url}"
                    ) from e
                wait = 2 ** attempt
                log.warning(f"Ollama connection error, retrying in {wait}s...")
                time.sleep(wait)

    def parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text  = "\n".join(lines[1:-1])
        return json.loads(text)
