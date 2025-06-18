# conductdoc/config.py
"""⚙️ Constants and configuration for the ConductDoc application.

This file centralizes all major settings, making it easy to change default
behaviors, directory names, and model choices in one place.
"""
from pathlib import Path

# --- Directory & File Names ---
# The main output directory for the generated static site.
OUTPUT_DIR_NAME = Path("generated_docs")

# The sub-directory within the output folder for code element reference pages.
REFERENCE_DIR_NAME = "reference"

# The hidden directory for storing temporary debug files (e.g., JSON dumps).
DEBUG_DIR_NAME = Path(".temp")

# The hidden directory for caching LLM responses to speed up subsequent runs.
CACHE_DIR_NAME = Path(".cache")


# --- Auto-detection Candidates ---
# A prioritized list of common names for documentation source folders.
DOCS_CANDIDATES = ["docs/source", "docs", "doc"]

# A prioritized list of common names for Python source code folders.
SRC_CANDIDATES = ["src", "."] # Search 'src' first, then the repo root.


# --- LLM Configuration ---
# The default local model to use with Ollama.
# qwen2:1.5b-instruct is chosen as a small, fast, and capable model.
LOCAL_LLM_MODEL = "qwen2.5-coder:3b"

# The default hosted model to use with OpenRouter.
# Claude 3 Haiku is known for its high speed, large context window, and low cost,
# making it an ideal choice for production-style summarization tasks.
OPENROUTER_LLM_MODEL = "openai/gpt-4.1-nano"