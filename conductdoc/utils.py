# conductdoc/utils.py
"""🛠️ A toolbox of shared utility functions used across the application."""
import json
import logging
import hashlib
import functools
from pathlib import Path
from typing import Dict, Set, Any, Callable

from .config import DEBUG_DIR_NAME, CACHE_DIR_NAME


def setup_logging():
    """Configures a clean and informative logging format for the console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: [%(asctime)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def save_debug_data(
    import_graph: Dict[Path, Set[Path]],
    module_map: Dict[str, Path],
    ast_map: Dict[Path, Any],
    project_root: Path,
    docs_context: str
):
    """
    Saves the core data structures from the crawling phase into human-readable
    files inside a .temp/ directory for easy debugging from the command line.
    """
    logging.info(f"💾 Saving debug data to files in '{DEBUG_DIR_NAME}/' directory...")
    DEBUG_DIR_NAME.mkdir(exist_ok=True)

    # Save the Import Graph as JSON
    readable_import_graph = {
        str(file.relative_to(project_root)): sorted([
            str(dep.relative_to(project_root)) for dep in dependencies
        ])
        for file, dependencies in import_graph.items()
    }
    import_graph_path = DEBUG_DIR_NAME / "debug_import_graph.json"
    with open(import_graph_path, "w", encoding="utf-8") as f:
        json.dump(readable_import_graph, f, indent=2)
    logging.info(f"  -> Saved '{import_graph_path}'")

    # Save the Module Map as JSON
    readable_module_map = {
        module_name: str(path.relative_to(project_root))
        for module_name, path in module_map.items()
    }
    module_map_path = DEBUG_DIR_NAME / "debug_module_map.json"
    with open(module_map_path, "w", encoding="utf-8") as f:
        json.dump(readable_module_map, f, indent=2, sort_keys=True)
    logging.info(f"  -> Saved '{module_map_path}'")
        
    # Save the Ingested Docs Context as an HTML file for easy viewing
    docs_context_path = DEBUG_DIR_NAME / "debug_docs_context.html"
    with open(docs_context_path, "w", encoding="utf-8") as f:
        f.write(docs_context)
    logging.info(f"  -> Saved '{docs_context_path}'")


def cache_llm_call(func: Callable) -> Callable:
    """
    A decorator that caches the results of an LLM call to a file-based cache.
    
    It creates a unique filename by hashing the combination of the prompt, the context,
    and the model name, ensuring that any change to the inputs results in a new
    cache entry.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> str:
        # 1. Robustly extract the key components from the function's keyword arguments.
        #    This ensures the decorated function must be called with these specific keywords.
        try:
            prompt = kwargs["prompt"]
            context = kwargs["context"]
            model_name = kwargs["model_name_for_cache"]
        except KeyError as e:
            # Provide a clear error if the decorated function is called incorrectly.
            raise TypeError(f"cache_llm_call requires '{e.args[0]}' as a keyword argument.") from e

        # 2. Create a stable, unique string from all components that affect the LLM's output.
        #    The prompt is a critical part of this key.
        key_string = f"prompt: {prompt} | context: {context} | model: {model_name}"
        
        # 3. Hash the key string to create a safe and unique filename.
        hash_key = hashlib.md5(key_string.encode('utf-8')).hexdigest()
        
        CACHE_DIR_NAME.mkdir(exist_ok=True)
        cache_file = CACHE_DIR_NAME / f"{hash_key}.txt"

        # 4. Check for a cache hit. If the file exists, return its content.
        if cache_file.is_file():
            logging.info(f"  -> ✅ Cache HIT for prompt: {prompt[:50]}...")
            return cache_file.read_text(encoding="utf-8")

        # 5. Cache miss: run the original, decorated function to get the live result.
        logging.info(f"  -> 🐢 Cache MISS for prompt: {prompt[:50]}...")
        result = func(*args, **kwargs)
        
        # 6. Save the new result to the cache file for future use.
        cache_file.write_text(result, encoding="utf-8")
        
        return result

    return wrapper