# conductdoc/crawler.py
"""🕷️ This module handles all crawling and data collection tasks.

- Cloning Git repositories
- Finding source and doc folders
- Parsing Python files with AST and building an import dependency graph
- Ingesting context from text files
"""

import ast
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple, Union

# Third-party imports
from docutils.core import publish_parts
import markdown

# Local imports
from .models import CodeElement
from .config import SRC_CANDIDATES, DOCS_CANDIDATES

# A definitive set of standard library modules for robust classification.
# Requires Python 3.10+. Falls back gracefully on older versions.
STANDARD_LIB_MODULES = set(sys.stdlib_module_names) if hasattr(sys, 'stdlib_module_names') else set()


def clone_repo(repo_url: str, target_dir: Path) -> None:
    """Clones a git repository into a specified directory."""
    logging.info(f"🚚 Cloning '{repo_url}' into '{target_dir}'...")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
            check=True, capture_output=True, text=True,
        )
        logging.info("✅ Repository cloned successfully.")
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Failed to clone repository. Git error: {e.stderr}")
        raise


def find_source_directory(root_path: Path) -> Optional[Path]:
    """Tries to auto-detect the main source directory."""
    logging.info("🕵️ Auto-detecting source directory...")
    for candidate in SRC_CANDIDATES:
        path = root_path / candidate
        # Heuristic: a directory containing an __init__.py is likely a package.
        if path.is_dir() and (path / "__init__.py").is_file():
            logging.info(f"👍 Found potential source directory at '{path}'.")
            return path
    logging.warning("🤔 Could not auto-detect a primary source directory.")
    return None


def find_docs_directory(root_path: Path) -> Optional[Path]:
    """Tries to auto-detect the main documentation directory."""
    logging.info("🕵️ Auto-detecting documentation directory...")
    for candidate in DOCS_CANDIDATES:
        path = root_path / candidate
        if path.is_dir():
            logging.info(f"👍 Found potential docs directory at '{path}'.")
            return path
    logging.warning("🤔 Could not auto-detect a documentation directory.")
    return None


def ingest_docs_context(docs_path: Path) -> str:
    """
    Recursively finds all .rst and .md files in the docs folder, converts
    them to HTML, and returns them as a single, labeled string of context.
    """
    logging.info(f"📚 Ingesting and converting ALL context from '{docs_path}'...")
    doc_files = sorted(list(docs_path.rglob("*.rst"))) + sorted(list(docs_path.rglob("*.md")))
    if not doc_files:
        logging.warning("🤔 No .rst or .md files found in docs folder.")
        return ""

    html_context = "<h1>Full Context from Existing Documentation</h1>\n"
    for filepath in doc_files:
        relative_path = filepath.relative_to(docs_path)
        logging.info(f"  -> Processing '{relative_path}'...")
        content = filepath.read_text(encoding="utf-8", errors="ignore")
        file_html = ""
        try:
            if filepath.suffix == ".rst":
                parts = publish_parts(source=content, writer_name='html', settings_overrides={'report_level': 5})
                file_html = parts.get('html_body', '')
            elif filepath.suffix == ".md":
                file_html = markdown.markdown(content)
            
            if file_html:
                html_context += f'<section data-source="{relative_path}">\n'
                html_context += f"  <h2>--- Context from: {relative_path} ---</h2>\n"
                html_context += "  " + file_html.replace('\n', '\n  ') + "\n"
                html_context += f"</section>\n\n"
        except Exception as e:
            logging.warning(f"⚠️ Could not process '{relative_path}': {e}")
    return html_context


def build_ast_and_module_map(src_path: Path) -> Tuple[Dict[Path, ast.AST], Dict[str, Path]]:
    """
    Crawls a directory to build two critical maps:
    1. A map from file paths to their parsed ASTs.
    2. A map from Python-style module names to their file paths.
    """
    logging.info(f"🌳 Building AST and Module maps for library at '{src_path}'...")
    ast_map: Dict[Path, ast.AST] = {}
    module_map: Dict[str, Path] = {}
    project_root = src_path.parent

    for py_file in sorted(src_path.rglob("*.py")):
        try:
            relative_path = py_file.relative_to(project_root)
            module_name = str(relative_path.with_suffix('')).replace('/', '.')
            if module_name.endswith('.__init__'):
                module_name = module_name.removesuffix('.__init__')
            
            source_code = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source_code, filename=str(py_file))
            
            ast_map[py_file] = tree
            module_map[module_name] = py_file
        except Exception as e:
            logging.warning(f"⚠️ Could not parse '{py_file.name}': {e}")
            
    logging.info(f"🗺️ Maps built successfully. Parsed {len(ast_map)} files.")
    return ast_map, module_map


def build_import_graph(ast_map: Dict[Path, ast.AST], module_map: Dict[str, Path]) -> Dict[Path, Set[Path]]:
    """Builds a dependency graph by analyzing ONLY internal import statements."""
    logging.info("🕸️  Building INTERNAL import dependency graph...")
    import_graph: Dict[Path, Set[Path]] = {filepath: set() for filepath in ast_map.keys()}
    filepath_to_module_name = {v: k for k, v in module_map.items()}

    for filepath, tree in ast_map.items():
        for node in ast.walk(tree):
            target_module_name = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target_module_name = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    current_module_parts = filepath_to_module_name.get(filepath, "").split('.')
                    if not current_module_parts: continue
                    base_parts = current_module_parts[:-(node.level)]
                    target_module_name = ".".join(base_parts + ([node.module] if node.module else []))
                else:
                    target_module_name = node.module

            if target_module_name:
                top_level = target_module_name.split('.')[0]
                if top_level in STANDARD_LIB_MODULES:
                    continue
                if target_module_name in module_map:
                    dependency_path = module_map[target_module_name]
                    import_graph[filepath].add(dependency_path)
    
    populated_entries = sum(1 for v in import_graph.values() if v)
    logging.info(f"✅ Internal import graph built. Found dependencies for {populated_entries} files.")
    return import_graph


class CodeVisitor(ast.NodeVisitor):
    """
    An AST visitor that recursively finds and extracts structured information
    about classes, methods, and functions from a Python source file.
    """
    def __init__(self, filepath: Path, source_text: str):
        self.filepath = filepath
        self.source_text = source_text
        self.elements: List[CodeElement] = []
        # This stack keeps track of our current class context, allowing for nested classes.
        self.class_context_stack: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        """
        Visits a class definition. It adds the class to our elements list
        and then recursively visits its children (e.g., methods, nested classes).
        """
        # Add the class itself to our list of elements.
        self.add_element(node, "class")
        
        # Push the current class name onto the stack to provide context for its children.
        self.class_context_stack.append(node.name)
        # Visit all children of this class node (methods, nested classes, etc.).
        self.generic_visit(node)
        # Once we're done with the class, pop it from the stack to exit its context.
        self.class_context_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """
        Visits a function or method definition. It determines if it's a regular
        function or a method within a class and extracts it accordingly.
        """
        element_type = "function"
        name_override = node.name
        
        # If the class context stack is not empty, this function is a method.
        if self.class_context_stack:
            # Check for @classmethod or @staticmethod decorators
            is_static = False
            is_class = False
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name):
                    if decorator.id == 'staticmethod':
                        is_static = True
                        break
                    if decorator.id == 'classmethod':
                        is_class = True
                        break
            
            if is_static:
                element_type = "staticmethod"
            elif is_class:
                element_type = "classmethod"
            else:
                element_type = "method"
            
            # Create a fully qualified name for the method, e.g., "MyClass.my_method"
            parent_class_name = ".".join(self.class_context_stack)
            name_override = f"{parent_class_name}.{node.name}"

        # Add the function/method to our list of elements.
        self.add_element(node, element_type, name_override=name_override)
        
        # We don't call generic_visit here to avoid capturing functions nested inside other functions for now.
        # This keeps the extracted element list cleaner.
    
    def add_element(
        self, 
        node: Union[ast.FunctionDef, ast.ClassDef], 
        element_type: str, 
        name_override: Optional[str] = None
    ):
        """
        A helper to create a CodeElement object from an AST node and add it to our list.
        """
        # Use the override name if provided (for methods), otherwise use the node's name.
        element_name = name_override if name_override else node.name
        
        try:
            # Use the robust ast.get_source_segment to get the exact source code.
            source_code = ast.get_source_segment(self.source_text, node)
            if source_code is None: 
                raise ValueError("Could not get source segment from AST node.")
                
            docstring = ast.get_docstring(node, clean=True) or ""
            end_lineno = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno is not None else node.lineno

            self.elements.append(CodeElement(
                name=element_name,
                type=element_type,
                filepath=self.filepath,
                lineno_start=node.lineno,
                lineno_end=end_lineno,
                source_code=source_code,
                docstring=docstring,
            ))
        except Exception as e:
            logging.warning(f"⚠️ Could not extract element '{element_name}' in {self.filepath}: {e}")

def crawl_source_code(src_path: Path) -> tuple[
    List[CodeElement], 
    Dict[Path, Set[Path]], 
    Dict[Path, ast.AST], 
    Dict[str, Path]
]:
    """The main crawling function that orchestrates all data collection."""
    logging.info(f"🐍 Starting source code crawl in '{src_path}'...")
    
    ast_map, module_map = build_ast_and_module_map(src_path)
    import_graph = build_import_graph(ast_map, module_map)

    all_elements: List[CodeElement] = []
    logging.info(f"🌿 Visiting {len(ast_map)} parsed files to extract code elements...")
    for filepath, tree in ast_map.items():
        try:
            source_text = filepath.read_text(encoding="utf-8")
            # Add parent pointers to the tree for more advanced analysis
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    setattr(child, 'parent', node)
            relative_filepath = filepath.relative_to(src_path.parent)
            visitor = CodeVisitor(filepath=relative_filepath, source_text=source_text)
            visitor.visit(tree)
            all_elements.extend(visitor.elements)
        except Exception as e:
            logging.error(f"💥 Failed to process file '{filepath.name}': {e}")
            
    logging.info(f"✅ Crawl complete. Found {len(all_elements)} code elements and built import graph.")
    return all_elements, import_graph, ast_map, module_map