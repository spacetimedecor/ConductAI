# main.py
"""
🚀 ConductDoc: Main Entry Point

This script orchestrates the entire AI documentation pipeline by calling
modules from the 'conductdoc' library in a clear, sequential manner.
"""
import argparse
import logging
import shutil
from pathlib import Path
import tempfile

# Local application imports
from conductdoc.utils import setup_logging, save_debug_data
from conductdoc.crawler import (
    clone_repo,
    find_source_directory,
    find_docs_directory,
    crawl_source_code,
    ingest_docs_context,
)
from conductdoc.analyzer import analyze_repo_with_rag
from conductdoc.generator import create_documentation_file
from conductdoc.config import OUTPUT_DIR_NAME, CACHE_DIR_NAME


def main():
    """The main entry point and orchestrator for the documentation pipeline."""
    setup_logging()
    
    parser = argparse.ArgumentParser(
        description="ConductDoc AI Documentation Generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--repo-url", required=True, help="URL of the Git repository to analyze.")
    parser.add_argument("--src-dir", help="(Optional) Override for the main source code directory.")
    parser.add_argument("--docs-dir", help="(Optional) Override for the documentation source directory.")
    parser.add_argument(
        "--llm-mode",
        choices=['local', 'openrouter'],
        default='local',
        help="Specify the LLM service: 'local' for Ollama or 'openrouter' for hosted models."
    )
    parser.add_argument(
        "--save-debug-data",
        action="store_true",
        help="Save intermediate crawler data to JSON files in the .temp/ directory for debugging."
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Delete all cached LLM responses in the .cache/ directory before running."
    )
    args = parser.parse_args()

    # Handle cache clearing before any main logic
    if args.clear_cache:
        if CACHE_DIR_NAME.exists():
            logging.info(f"🔥 Clearing LLM response cache at '{CACHE_DIR_NAME}'...")
            shutil.rmtree(CACHE_DIR_NAME)
            logging.info("✅ Cache cleared.")
        else:
            logging.info("✨ Cache directory does not exist, nothing to clear.")

    try:
        # Use a temporary directory for cloning to ensure automatic cleanup
        with tempfile.TemporaryDirectory() as temp_dir_str:
            repo_path = Path(temp_dir_str)
            
            # === PHASE 1: CRAWL & COLLECT 🕷️ ===
            clone_repo(args.repo_url, repo_path)
            
            src_path = repo_path / args.src_dir if args.src_dir else find_source_directory(repo_path)
            docs_path = repo_path / args.docs_dir if args.docs_dir else find_docs_directory(repo_path)
            
            if not src_path or not src_path.is_dir():
                logging.error(f"❌ Source directory not found. Cannot proceed. Attempted path: {src_path}")
                return

            all_elements, import_graph, ast_map, module_map = crawl_source_code(src_path)
            docs_context = ingest_docs_context(docs_path) if docs_path and docs_path.is_dir() else ""
            
            if args.save_debug_data:
                save_debug_data(
                    import_graph=import_graph,
                    module_map=module_map,
                    ast_map=ast_map,
                    project_root=src_path.parent,
                    docs_context=docs_context
                )

            readme_content = (repo_path / "README.md").read_text(encoding="utf-8") if (repo_path / "README.md").is_file() else ""
            
            # === PHASE 2: ANALYZE 🧠 ===
            analysis_result, all_elements_with_docs = analyze_repo_with_rag(
                elements=all_elements, 
                import_graph=import_graph,
                project_root=src_path.parent,
                readme_content=readme_content, 
                docs_context=docs_context,
                llm_mode=args.llm_mode
            )
            
            # === PHASE 3: GENERATE 📝 ===
            create_documentation_file(analysis_result, all_elements_with_docs)

            logging.info(f"✅ Success! Documentation generated in '{OUTPUT_DIR_NAME.resolve()}'")
            logging.info(f"👉 To view, open '{OUTPUT_DIR_NAME.resolve() / 'documentation.html'}' in your browser.")

    except Exception as e:
        logging.critical(f"💥 A critical error occurred during the pipeline: {e}", exc_info=True)


if __name__ == "__main__":
    main()