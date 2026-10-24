"""The no-external-AI policy as data.

This module is the single source of truth for what the architectural
compliance checks treat as prohibited. It is deliberately excluded from the
source scan because it has to name the things it prohibits.

The lists are a denylist, so they catch known providers and SDKs; they cannot
prove the absence of every possible AI integration. Code review and the
dependency audit in docs/COMPLIANCE.md cover the rest.
"""

from __future__ import annotations

import re

# Python distributions (normalised: lowercase, "-" for "_" and ".") that
# provide hosted-model clients, local LLM runtimes, neural NLP pipelines or
# embedding models.
PROHIBITED_PYTHON_PACKAGES: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "google-generativeai",
        "google-genai",
        "google-cloud-aiplatform",
        "vertexai",
        "cohere",
        "mistralai",
        "groq",
        "together",
        "replicate",
        "voyageai",
        "fireworks-ai",
        "ai21",
        "litellm",
        "instructor",
        "huggingface-hub",
        "transformers",
        "sentence-transformers",
        "tokenizers",
        "accelerate",
        "torch",
        "tensorflow",
        "keras",
        "jax",
        "onnxruntime",
        "ctranslate2",
        "llama-cpp-python",
        "llama-index",
        "langchain",
        "langchain-core",
        "langchain-community",
        "langchain-openai",
        "langchain-anthropic",
        "ollama",
        "gpt4all",
        "vllm",
        "spacy",
        "stanza",
        "flair",
        "allennlp",
        "easyocr",
        "paddleocr",
        "doctr",
        "python-doctr",
        "unstructured",
        "fastembed",
        "chromadb",
    }
)

# Python import roots corresponding to the packages above.
PROHIBITED_PYTHON_IMPORTS: frozenset[str] = frozenset(
    {
        "openai",
        "anthropic",
        "google.generativeai",
        "google.genai",
        "google.cloud.aiplatform",
        "vertexai",
        "cohere",
        "mistralai",
        "groq",
        "together",
        "replicate",
        "voyageai",
        "litellm",
        "instructor",
        "huggingface_hub",
        "transformers",
        "sentence_transformers",
        "tokenizers",
        "torch",
        "tensorflow",
        "keras",
        "jax",
        "onnxruntime",
        "ctranslate2",
        "llama_cpp",
        "llama_index",
        "langchain",
        "langchain_core",
        "langchain_community",
        "ollama",
        "gpt4all",
        "vllm",
        "spacy",
        "stanza",
        "flair",
        "easyocr",
        "paddleocr",
        "doctr",
        "unstructured",
        "fastembed",
        "chromadb",
    }
)

# npm packages (exact names or scope prefixes ending in "/").
PROHIBITED_NPM_PACKAGES: frozenset[str] = frozenset(
    {
        "openai",
        "@anthropic-ai/",
        "ai",
        "@ai-sdk/",
        "@google/generative-ai",
        "@google/genai",
        "@google-cloud/vertexai",
        "langchain",
        "@langchain/",
        "llamaindex",
        "@huggingface/",
        "@xenova/transformers",
        "cohere-ai",
        "@mistralai/",
        "groq-sdk",
        "replicate",
        "together-ai",
        "ollama",
        "@tensorflow/",
        "onnxruntime-node",
        "onnxruntime-web",
    }
)

# Hostnames of hosted inference endpoints and default local LLM servers.
PROHIBITED_HOST_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"api\.openai\.com",
        r"[a-z0-9-]+\.openai\.azure\.com",
        r"api\.anthropic\.com",
        r"generativelanguage\.googleapis\.com",
        r"aiplatform\.googleapis\.com",
        r"api-inference\.huggingface\.co",
        r"router\.huggingface\.co",
        r"api\.cohere\.(ai|com)",
        r"api\.mistral\.ai",
        r"api\.groq\.com",
        r"api\.together\.(xyz|ai)",
        r"api\.replicate\.com",
        r"api\.deepseek\.com",
        r"api\.fireworks\.ai",
        r"api\.perplexity\.ai",
        r"api\.voyageai\.com",
        r"bedrock-runtime\.[a-z0-9-]+\.amazonaws\.com",
        r"openrouter\.ai",
        # Default ports of local LLM servers (Ollama, LM Studio).
        r"(localhost|127\.0\.0\.1):(11434|1234)\b",
    )
)

# Environment variables whose presence indicates an AI provider is configured.
PROHIBITED_ENV_VARS: frozenset[str] = frozenset(
    {
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_API_KEY",
        "HF_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
        "HUGGINGFACEHUB_API_TOKEN",
        "COHERE_API_KEY",
        "MISTRAL_API_KEY",
        "GROQ_API_KEY",
        "TOGETHER_API_KEY",
        "REPLICATE_API_TOKEN",
        "DEEPSEEK_API_KEY",
        "FIREWORKS_API_KEY",
        "PERPLEXITY_API_KEY",
        "VOYAGE_API_KEY",
        "OPENROUTER_API_KEY",
        "OLLAMA_HOST",
    }
)

# Modules that open network connections. Intelligence packages must not import
# them: answers, retrieval and analysis have to work offline.
NETWORK_MODULES: frozenset[str] = frozenset(
    {
        "socket",
        "ssl",
        "http.client",
        "urllib.request",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "grpc",
        "boto3",
        "botocore",
    }
)

# Backend packages that make up the academic intelligence pipeline. They are
# checked for network imports in addition to the global AI checks.
INTELLIGENCE_PACKAGES: tuple[str, ...] = (
    "scholariq.domain",
    "scholariq.ingestion",
    "scholariq.analytics",
    "scholariq.knowledge",
    "scholariq.retrieval",
    "scholariq.nlu",
    "scholariq.answering",
    "scholariq.tutoring",
    "scholariq.planning",
    "scholariq.diagnostics",
    "scholariq.exams",
)


def normalise_dist_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def is_prohibited_npm(name: str) -> bool:
    for entry in PROHIBITED_NPM_PACKAGES:
        if entry.endswith("/"):
            if name.startswith(entry):
                return True
        elif name == entry:
            return True
    return False


def is_prohibited_import(module: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in PROHIBITED_PYTHON_IMPORTS)


def present_prohibited_env_vars(environ: dict[str, str]) -> list[str]:
    """Names of prohibited variables that are set to a non-empty value."""
    return sorted(k for k in PROHIBITED_ENV_VARS if environ.get(k))
