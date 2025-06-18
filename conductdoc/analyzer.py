"""
🧠 This module handles all interactions with AI models. It uses a dual-summary
strategy within a recursive RAG pipeline to generate documentation at multiple
levels of detail.
"""
import logging
import os
import json
import textwrap
import html
from typing import List, Dict, Set, Any
from pathlib import Path
from collections import defaultdict

# Third-party imports
from openai import OpenAI
from dotenv import load_dotenv

# Local imports
from .models import CodeElement, AnalysisResult
from .retriever import Retriever
from .utils import cache_llm_call
from .config import LOCAL_LLM_MODEL, OPENROUTER_LLM_MODEL

# --- Unified, Cached LLM Interaction ---

@cache_llm_call
def get_llm_response(prompt: str, context: str, mode: str, model_name_for_cache: str) -> str:
    """
    Sends a prompt and context to an LLM and returns the response.
    This function is wrapped by the @cache_llm_call decorator, so results
    are cached to disk based on the arguments.
    """
    full_prompt = f"{prompt}\n\nHere is the context to use:\n\n---\n{context}\n---"
    
    if mode == 'openrouter':
        load_dotenv()
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logging.error("❌ OPENROUTER_API_KEY not found in .env file for openrouter mode.")
            return "<p><strong>Error:</strong> OpenRouter API key not configured.</p>"
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    else: # Default to local Ollama
        client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')

    try:
        logging.info(f"  -> Sending prompt to {mode} model ({model_name_for_cache})...")
        response = client.chat.completions.create(
            model=model_name_for_cache,
            messages=[
                {"role": "system", "content": "You are an expert technical writer and software engineer. You generate clear, concise documentation in HTML format. You ONLY output the requested HTML, nothing else."},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logging.error(f"❌ Could not connect to the '{mode}' LLM service. Error: {e}")
        return f"<p><strong>Error:</strong> Could not connect to '{mode}' LLM. Details: {e}</p>"

# --- Recursive Summarization Logic ---

def _summarize_code_file(
    file_path: Path, 
    elements_in_file: List[CodeElement], 
    retriever: Retriever,
    llm_mode: str,
    model_name: str
) -> Dict[str, str]:
    """
    Generates TWO summaries for a single Python file:
    1. A concise 'abstractive' summary for the recursive process.
    2. A 'detailed' summary for the final documentation page.
    """
    class_names = [el.name for el in elements_in_file if el.type == 'class']
    function_names = [el.name for el in elements_in_file if el.type == 'function']
    
    query = f"Detailed purpose and contents of the Python module '{file_path}'"
    # SORT the retrieved chunks to ensure a deterministic context.
    retrieved_chunks = sorted(retriever.retrieve(query, k=5))
    
    context = f"File Path: {file_path}\nClasses: {', '.join(class_names)}\nFunctions: {', '.join(function_names)}\nRelevant context:\n- {'\n- '.join(retrieved_chunks)}"

    prompt_abstractive = f"Write a very concise, one-sentence summary in an HTML `<p>` tag explaining the single primary purpose of the Python file '{file_path}'. Output only the `<p>` tag."
    abstractive_summary = get_llm_response(prompt=prompt_abstractive, context=context, mode=llm_mode, model_name_for_cache=model_name)

    prompt_detailed = f"""
    You are a technical writer documenting the Python file '{file_path}'.
    Based on the context, provide a detailed summary in HTML format. The summary should:
    1. Start with a paragraph explaining the file's overall purpose.
    2. If there are classes or functions, include a bulleted list (`<ul>`) of the most important ones.
    3. For each item in the list, briefly explain its role.
    Do not include a main `<h1>` title.
    """
    detailed_summary = get_llm_response(prompt=prompt_detailed, context=context, mode=llm_mode, model_name_for_cache=model_name)
    
    return {"abstractive": abstractive_summary, "detailed": detailed_summary}

def _recursively_summarize_directory(
    dir_path: Path,
    fs_tree_node: Dict[str, Any],
    retriever: Retriever,
    llm_mode: str,
    model_name: str,
    file_summaries_collector: Dict[Path, str],
    module_summaries_collector: Dict[Path, str] 
) -> Dict[str, Any]:
    """
    (Helper) Recursively generates summaries, processing subdirectories before files.
    """
    summary_node = {"summary": "", "children": {}}
    child_summary_contexts = []

    # 1. Process subdirectories first (the recursive step)
    for dir_name, dir_content in sorted(fs_tree_node.get("dirs", {}).items()):
        child_path = dir_path / dir_name
        logging.info(f"  -> Descending into directory: {child_path}")
        child_summary_node = _recursively_summarize_directory(
            child_path, dir_content, retriever, llm_mode, model_name, 
            file_summaries_collector, module_summaries_collector
        )
        summary_node["children"][dir_name] = child_summary_node
        child_summary_contexts.append(f"Submodule '{dir_name}': {child_summary_node['summary']}")

    # 2. Process files at this level second (the base case for this level)
    for file_name, file_elements in sorted(fs_tree_node.get("files", {}).items()):
        child_path = dir_path / file_name
        logging.info(f"  -> Summarizing file: {child_path}")
        
        summaries = _summarize_code_file(child_path, file_elements, retriever, llm_mode, model_name)
        
        summary_node["children"][file_name] = {"summary": summaries["detailed"], "children": {}}
        
        abstractive_summary = summaries["abstractive"]
        file_summaries_collector[child_path] = abstractive_summary
        
        child_summary_contexts.append(f"File '{file_name}': {abstractive_summary}")
        retriever.add_chunks([f"AI-Generated Summary for file '{child_path}': {abstractive_summary}"])
        
    # 3. Summarize the current directory
    if child_summary_contexts:
        query = f"High-level summary for the Python submodule '{dir_path}'"
        # SORT the retrieved chunks to ensure a deterministic context.
        retrieved_chunks = sorted(retriever.retrieve(query, k=7))
        context = f"This is submodule '{dir_path}'. Relevant context, including summaries of its contents:\n- " + "\n- ".join(retrieved_chunks)
        prompt = f"Based on its contents' summaries, write a one-paragraph summary in an HTML `<p>` tag for the submodule '{dir_path}'. Explain its overall responsibility. Output only the `<p>` tag."
        dir_summary = get_llm_response(prompt=prompt, context=context, mode=llm_mode, model_name_for_cache=model_name)
        summary_node["summary"] = dir_summary
        
        module_summaries_collector[dir_path] = dir_summary

        retriever.add_chunks([f"AI-Generated Summary for module '{dir_path}': {dir_summary}"])
        
    return summary_node

def _format_summary_tree_to_html(summary_tree: Dict[str, Any], level: int = 0) -> str:
    """(Helper) Recursively converts the summary tree into a nested HTML list."""
    html = ""
    sorted_children = sorted(summary_tree.items(), key=lambda item: not item[1].get("children"))
    for name, node in sorted_children:
        html += f"<li style='margin-left: {level * 25}px;'>"
        html += f"<strong>{name}:</strong> {node.get('summary', 'N/A')}"
        if node.get("children"):
            html += "<ul>"
            html += _format_summary_tree_to_html(node["children"], level + 1)
            html += "</ul>"
        html += "</li>"
    return html

def generate_recursive_summary(
    elements: List[CodeElement], 
    retriever: Retriever, 
    readme_content: str, 
    llm_mode: str, 
    model_name: str
) -> tuple[str, str, Dict[Path, str], Dict[Path, str]]:
    """
    Generates a deep, recursive summary of the entire library structure.
    
    Returns:
        - The final, full HTML summary for the documentation page.
        - The raw text of the top-level summary.
        - A dictionary of file-level summaries.
        - A dictionary of module-level summaries.
    """
    logging.info("🤖 Generating deep recursive summary by building up understanding...")

    file_summaries: Dict[Path, str] = {}
    module_summaries: Dict[Path, str] = {}
    
    elements_by_file: Dict[Path, List[CodeElement]] = defaultdict(list)
    for el in elements:
        elements_by_file[el.filepath].append(el)
        
    fs_tree = {"dirs": {}, "files": {}}
    for path in sorted(elements_by_file.keys()):
        current_level = fs_tree
        for part in path.parts[:-1]:
            current_level = current_level["dirs"].setdefault(part, {"dirs": {}, "files": {}})
        filename = path.parts[-1]
        current_level["files"][filename] = elements_by_file[path]

    if not fs_tree["dirs"]: 
        return "<p>No directories found to summarize.</p>", "", {}, {}
        
    root_name = list(fs_tree["dirs"].keys())[0]
    root_node_content = fs_tree["dirs"][root_name]
    
    summary_tree = _recursively_summarize_directory(
        Path(root_name), root_node_content, retriever, llm_mode, model_name, 
        file_summaries, module_summaries
    )

    top_level_prompt = "You are a senior technical writer. Using the project's README and the overall structural summary, write a comprehensive, multi-paragraph overview of the entire library in HTML format. Start with a high-level explanation of its purpose. Then, briefly describe the role of its key submodules."
    top_level_context = f"README:\n{readme_content}\n\nOverall structure summary:\n{summary_tree.get('summary', 'Not available.')}"
    final_summary = get_llm_response(prompt=top_level_prompt, context=top_level_context, mode=llm_mode, model_name_for_cache=model_name)
    
    html_output = f"<h1>Library Overview</h1>{final_summary}"
    html_output += "<h2>Detailed Architectural Summary</h2>"
    html_output += f"<ul>{_format_summary_tree_to_html({root_name: summary_tree})}</ul>"

    return html_output, final_summary, file_summaries, module_summaries


def generate_ai_architecture_diagram(
    import_graph: Dict[Path, Set[Path]],
    top_level_summary_text: str,
    module_summaries: Dict[Path, str],
    file_summaries: Dict[Path, str],
    project_root: Path,
    llm_mode: str,
    model_name: str
) -> str:
    """
    Generates an interactive D3.js hierarchy diagram for a library's source code
    with popovers containing summaries for each module and file.
    """
    logging.info("🌳 Generating interactive D3.js library hierarchy diagram...")

    # Build hierarchical data structure
    hierarchy_data = _build_hierarchy_data(
        file_summaries, module_summaries, project_root
    )
    
    # Count import relationships for each file
    import_counts = _calculate_import_metrics(import_graph, project_root)
    
    # Prepare context for LLM
    structure_summary = _describe_structure(hierarchy_data)
    
    full_context = f"""
LIBRARY OVERVIEW:
{top_level_summary_text}

DIRECTORY STRUCTURE:
{structure_summary}

IMPORT RELATIONSHIPS:
{len(import_graph)} files with import dependencies

FILE SUMMARIES:
{_format_summaries(file_summaries, project_root, "FILE")}

MODULE SUMMARIES:
{_format_summaries(module_summaries, project_root, "MODULE")}
"""

    prompt = f"""
You are creating an interactive D3.js library source code visualization. Generate a complete HTML page with an interactive tree diagram showing the library's architecture.

**REQUIREMENTS:**

1. **HTML Structure**: Complete HTML page with D3.js loaded from CDN
2. **Interactive Tree**: Collapsible tree diagram using D3.js hierarchy layout
3. **Node Types**: 
   - 📁 Directories (collapsible)
   - 🐍 Python modules (.py files)
   - 📄 Other files (__init__.py, setup.py, etc.)
4. **Popovers**: Interactive tooltips showing full summaries on hover
5. **Styling**: Clean, modern design suitable for library documentation
6. **Responsiveness**: Works on different screen sizes

**TECHNICAL SPECS:**

- Use D3.js v7 from CDN
- Tree layout with smooth transitions
- Click to expand/collapse directories
- Hover for detailed summary popovers
- Color coding: directories (blue), Python files (green), config files (orange)
- Include import count badges for files with many dependencies
- Zoom and pan functionality for large trees

**DATA STRUCTURE:**
Transform the provided summaries into a nested JSON structure where each node has:
- name: file/directory name
- type: "directory", "python", "config", or "other"
- summary: the actual summary from the provided context
- children: array of child nodes (for directories)
- importCount: number of imports (for files)

**POPOVER CONTENT:**
- File/directory name
- Type and purpose
- Full summary from the provided context
- Import count (if applicable)
- Path information

**EXAMPLE STRUCTURE:**
```json
{{
  "name": "library_root",
  "type": "directory", 
  "summary": "Main library package",
  "children": [
    {{
      "name": "core",
      "type": "directory",
      "summary": "Core functionality modules",
      "children": [...]
    }},
    {{
      "name": "utils.py",
      "type": "python",
      "summary": "Utility functions and helpers",
      "importCount": 3
    }}
  ]
}}
```

**STYLING REQUIREMENTS:**
- Modern, clean design
- Subtle shadows and gradients
- Smooth animations
- Readable typography
- Professional color scheme
- Responsive layout

Generate the complete HTML page with embedded CSS and JavaScript. Use the actual summaries provided in the context below to populate the tree data.

CONTEXT:
{full_context}
"""
    response = get_llm_response(prompt=prompt, context=full_context, mode=llm_mode, model_name_for_cache=model_name)
    if not response.strip():
        logging.error("❌ LLM returned an empty response for the architecture diagram.")
        return "<p><strong>Error:</strong> Could not generate architecture diagram.</p>"
    
    response = response.replace("```html", "").replace("```", "").strip()
    
    return response


def _build_hierarchy_data(file_summaries: Dict[Path, str], module_summaries: Dict[Path, str], project_root: Path) -> dict:
    """Build nested dictionary representing the directory hierarchy."""
    # Use a consistent name for the root to ensure cache consistency across temp directories
    hierarchy = {"name": "project_root", "type": "directory", "children": []}
    
    all_items = {}
    
    # Add files
    for path, summary in file_summaries.items():
        rel_path = path
        all_items[rel_path] = {"summary": summary, "type": _get_file_type(path), "is_file": True}
    
    # Add modules (directories)
    for path, summary in module_summaries.items():
        rel_path = path
        all_items[rel_path] = {"summary": summary, "type": "directory", "is_file": False}
    
    # Build nested structure, SORTING by path to ensure deterministic order.
    # The key is item[0], which is the Path object. Path objects are comparable.
    for rel_path, item_data in sorted(all_items.items(), key=lambda item: item[0]):
        _insert_into_hierarchy(hierarchy, rel_path.parts, item_data)
    
    return hierarchy


def _insert_into_hierarchy(hierarchy: dict, path_parts: tuple, item_data: dict):
    """Insert an item into the nested hierarchy structure."""
    current = hierarchy
    
    # Navigate to the correct location
    for part in path_parts[:-1]:
        # Find or create the directory
        found = False
        for child in current.get("children", []):
            if child["name"] == part and child["type"] == "directory":
                current = child
                found = True
                break
        
        if not found:
            new_dir = {"name": part, "type": "directory", "children": []}
            current.setdefault("children", []).append(new_dir)
            current = new_dir
    
    # Add the final item
    final_name = path_parts[-1]
    final_item = {
        "name": final_name,
        "type": item_data["type"],
        "summary": item_data["summary"]
    }
    
    if not item_data["is_file"]:
        final_item["children"] = []
    
    current.setdefault("children", []).append(final_item)


def _get_file_type(path: Path) -> str:
    """Determine the type of file based on its extension and name."""
    if path.suffix == ".py":
        if path.name == "__init__.py":
            return "init"
        return "python"
    elif path.name in ["setup.py", "setup.cfg", "pyproject.toml", "requirements.txt"]:
        return "config"
    elif path.suffix in [".md", ".rst", ".txt"]:
        return "docs"
    elif path.suffix in [".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"]:
        return "config"
    else:
        return "other"


def _calculate_import_metrics(import_graph: Dict[Path, Set[Path]], project_root: Path) -> Dict[str, int]:
    """Calculate import counts for each file."""
    import_counts = {}
    for file_path, imports in import_graph.items():
        rel_path = str(file_path)
        import_counts[rel_path] = len(imports)
    return import_counts


def _describe_structure(hierarchy: dict, level: int = 0) -> str:
    """Create a text description of the hierarchy structure."""
    indent = "  " * level
    description = f"{indent}{hierarchy['name']} ({hierarchy['type']})\n"
    
    # Sort children by name to ensure a deterministic text output
    sorted_children = sorted(hierarchy.get("children", []), key=lambda child: child['name'])
    
    for child in sorted_children:
        description += _describe_structure(child, level + 1)
    
    return description


def _format_summaries(summaries: Dict[Path, str], project_root: Path, prefix: str) -> str:
    """Format summaries for context."""
    # Use sorted() to guarantee a deterministic order for the context string.
    # We sort by the key (the Path object), which is a reliable way to order the items.
    return "\n".join([
        f'{prefix}: "{path}" - {summary}'
        for path, summary in sorted(summaries.items(), key=lambda item: item[0])
    ])


def generate_code_examples(
    top_level_summary_text: str, 
    retriever: Retriever, 
    llm_mode: str, 
    model_name: str
) -> Dict[str, str]: # <<< CHANGE 1: Return type is now Dict[str, str]
    """
    Generates a series of code examples and returns them as a dictionary.
    
    Returns:
        A dictionary where keys are the example task descriptions (e.g., "Create a basic animation")
        and values are the corresponding HTML code examples.
    """
    logging.info("🤖 Generating code examples based on high-level summary...")

    # --- Step 1: Identify realistic use cases ---
    capability_prompt = f"""
    Based on the following summary of a Python library, identify 5 to 7 specific, realistic tasks a user would want to accomplish.
    Return ONLY a JSON object with this structure: {{"example_tasks": ["Specific task 1", "Specific task 2", ...]}}
    """
    try:
        capability_response = get_llm_response(prompt=capability_prompt, context=top_level_summary_text, mode=llm_mode, model_name_for_cache=model_name)
        cleaned_response = capability_response.strip().replace("```json", "").replace("```", "").strip()
        capability_data = json.loads(cleaned_response)
        example_topics = capability_data.get("example_tasks", [])
        if not isinstance(example_topics, list): raise ValueError("example_tasks is not a list.")
        logging.info(f"  -> Identified {len(example_topics)} realistic example tasks.")
    except (json.JSONDecodeError, ValueError) as e:
        logging.error(f"❌ Failed to parse capability analysis from LLM response: {e}")
        return {"Error": f"<p>Could not automatically analyze capabilities for examples.</p>"}

    # --- Step 2: Generate an example for each identified task ---
    # CHANGE 2: Create a dictionary to hold the results
    generated_examples: Dict[str, str] = {}
    
    for i, topic in enumerate(example_topics, 1):
        logging.info(f"  -> Generating example {i}/{len(example_topics)} for: '{topic}'...")
        
        # Use RAG to get relevant context for the specific task
        task_context_chunks = sorted(retriever.retrieve(f"How to {topic} with code examples", k=10))
        task_context = "\n- ".join(task_context_chunks)
        
        example_prompt = f"""
        You are creating a code example for a Python library to demonstrate the task: "{topic}".
        CRITICAL: Use ONLY functions, classes, and methods from the provided codebase context. The code must be self-contained and runnable.
        Response MUST be valid HTML containing:
        1. A `<p>` tag explaining what the code does.
        2. A `<pre><code>` block with the well-commented Python code.
        ONLY output this HTML content.
        """
        
        example_html = get_llm_response(prompt=example_prompt, context=task_context, mode=llm_mode, model_name_for_cache=model_name)
        
        # CHANGE 3: Add the result to the dictionary
        generated_examples[topic] = example_html

    logging.info("✅ All library-specific code examples generated.")
    return generated_examples

# --- Main Analysis Orchestrator ---

def analyze_repo_with_rag(
    elements: List[CodeElement],
    import_graph: Dict[Path, Set[Path]],
    project_root: Path,
    readme_content: str,
    docs_context: str,
    llm_mode: str
) -> tuple[AnalysisResult, List[CodeElement]]:
    
    model_name = OPENROUTER_LLM_MODEL if llm_mode == 'openrouter' else LOCAL_LLM_MODEL

    retriever = Retriever()
    retriever.build_initial_indexes(docs_html=docs_context, code_elements=elements)

    summary, top_level_summary_text, file_summaries, module_summaries = generate_recursive_summary(
        elements, retriever, readme_content, llm_mode, model_name
    )

    architecture_diagram = generate_ai_architecture_diagram(
        import_graph=import_graph,
        llm_mode='openrouter',  # Claude is an OpenRouter model
        model_name="anthropic/claude-sonnet-4",
        top_level_summary_text=top_level_summary_text,
        module_summaries=module_summaries,
        file_summaries=file_summaries,
        project_root=project_root
    )
    
    examples = generate_code_examples(
        top_level_summary_text, retriever, 'openrouter', "google/gemini-2.5-flash"  # Gemini is also OpenRouter
    )
    
    analysis_result = AnalysisResult(
        summary=summary,
        architecture_diagram=architecture_diagram,
        examples=examples,
    )

    return analysis_result, elements