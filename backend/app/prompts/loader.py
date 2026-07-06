from functools import lru_cache
from importlib.resources import files


@lru_cache
def load_prompt(filename: str) -> str:
    return files("app.prompts").joinpath(filename).read_text(encoding="utf-8").strip()

