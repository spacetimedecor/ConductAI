import html
import re
from collections import defaultdict
from pathlib import Path, PosixPath
from typing import List, Dict, Any

from conductdoc.models import AnalysisResult, CodeElement



# ==============================================================================
# 2. HELPER & GENERATOR FUNCTIONS
# ==============================================================================

def _group_elements_by_filepath(elements: List[CodeElement]) -> Dict[str, List[CodeElement]]:
    """Groups code elements by their file path and sorts them by line number."""
    grouped = defaultdict(list)
    for element in elements:
        grouped[str(element.filepath)].append(element)
    
    for filepath in grouped:
        grouped[filepath].sort(key=lambda e: e.lineno_start)
        
    return dict(sorted(grouped.items()))

def _generate_anchor(text: str) -> str:
    """Creates a URL-friendly anchor string from any text."""
    text = text.lower()
    text = re.sub(r'[\\/.:*?"<>|]+', '-', text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text.strip())
    return text

def _parse_d3_diagram(d3_html: str) -> Dict[str, str]:
    """Extracts style, body divs, and script content from a full D3 HTML file."""
    style_match = re.search(r'<style>(.*?)</style>', d3_html, re.DOTALL)
    body_match = re.search(r'<body>(.*?)</body>', d3_html, re.DOTALL)
    
    style = style_match.group(1) if style_match else ''
    body_content = body_match.group(1) if body_match else ''

    script_match = re.search(r'<script>(?!</script>)(.*?)</script>', body_content, re.DOTALL)
    script = script_match.group(1) if script_match else ''
    
    div_content = re.sub(r'<script>.*?</script>', '', body_content, flags=re.DOTALL).strip()

    return {'style': style, 'divs': div_content, 'script': script}

def generate_static_site(analysis_result: AnalysisResult, all_elements_with_docs: List[CodeElement]) -> str:
    """
    Generates a single, self-contained HTML file for library documentation.
    This function *only* returns the HTML string.
    """
    # 1. Prepare data by grouping and parsing
    api_data = _group_elements_by_filepath(all_elements_with_docs)
    d3_parts = _parse_d3_diagram(analysis_result.architecture_diagram)

    # 2. Generate HTML for dynamic sections
    api_nav_html = "<ul>"
    for filepath in api_data.keys():
        anchor = _generate_anchor(f"file-{{filepath}}")
        api_nav_html += f'<li><a href="#{{anchor}}">{{filepath}}</a></li>'
    api_nav_html += "</ul>"
    
    api_content_html = ""
    for filepath, elements in api_data.items():
        file_anchor = _generate_anchor(f"file-{{filepath}}")
        api_content_html += f'<article id="{{file_anchor}}" class="api-file-section">'
        api_content_html += f'<h3 class="api-filepath">{{filepath}}</h3>'
        
        for element in elements:
            element_anchor = _generate_anchor(f"api-{{filepath}}-{{element.name}}")
            safe_docstring = f"<blockquote>{{html.escape(element.docstring)}}</blockquote>" if element.docstring else ""
            safe_source_code = html.escape(element.source_code)
            
            api_content_html += f"""
            <div class="api-element" id="{{element_anchor}}">
                <div class="api-element-header">
                    <h4>
                        <span class="api-element-name">{{html.escape(element.name)}}</span>
                        <span class="api-element-type">{{html.escape(element.type)}}</span>
                    </h4>
                    <span class="api-element-location">{{html.escape(str(element.filepath))}}:{{element.lineno_start}}-{{element.lineno_end}}</span>
                </div>
                <div class="api-element-body">
                    {{safe_docstring}}
                    <div class="code-container">
                        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
                        <pre><code>{{safe_source_code}}</code></pre>
                    </div>
                </div>
            </div>
            """
        api_content_html += '</article>'
        
    examples_html = ""
    for description, code_html in analysis_result.examples.items():
        modified_code_html = code_html.replace(
            "<pre>",
            '<div class="code-container"><button class="copy-btn" onclick="copyCode(this)">Copy</button><pre>',
            1
        ).replace(
            "</pre>",
            "</pre></div>",
            1
        )
        examples_html += f"""
        <article class="example-item">
            <h3>{{html.escape(description)}}</h3>
            {{modified_code_html}}
        </article>
        """

    # 3. Assign template variables to match the new template format
    d3_styles = d3_parts['style']
    summary_html = analysis_result.summary
    d3_divs = d3_parts['divs']
    d3_script = d3_parts['script']
    
    # 4. Assemble the final HTML using the new template
    final_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manim Library Documentation</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        /* --- General & Layout --- */
        :root {{
            --bg-color: #111827;
            --text-color: #d1d5db;
            --header-bg: #1f2937;
            --accent-color: #38bdf8;
            --accent-hover: #7dd3fc;
            --border-color: #374151;
            --code-bg: #161b22;
            --nav-height: 65px;
        }}

        html {{ scroll-behavior: smooth; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            line-height: 1.7;
        }}

        .container {{ max-width: 1280px; margin: 0 auto; padding: 20px; }}
        h1, h2, h3, h4 {{ color: #f9fafb; margin-top: 1.5em; margin-bottom: 0.5em; letter-spacing: -0.5px; }}
        h1 {{ font-size: 2.8em; border-bottom: 2px solid var(--accent-color); padding-bottom: 0.3em; }}
        h2 {{ font-size: 2.2em; border-bottom: 1px solid var(--border-color); padding-bottom: 0.2em; }}
        h3 {{ font-size: 1.6em; color: var(--accent-color); }}
        h4 {{ font-size: 1.25em; }}
        a {{ color: var(--accent-color); text-decoration: none; transition: color 0.2s; }}
        a:hover {{ color: var(--accent-hover); text-decoration: underline; }}
        section {{ padding-top: var(--nav-height); margin-top: calc(-1 * var(--nav-height)); padding-bottom: 40px; border-bottom: 1px solid var(--border-color); }}
        section:last-child {{ border-bottom: none; }}
        
        /* --- Navigation --- */
        .main-nav {{
            background-color: rgba(31, 41, 55, 0.8);
            backdrop-filter: blur(10px);
            padding: 0;
            height: var(--nav-height);
            position: sticky;
            top: 0;
            z-index: 1000;
            border-bottom: 1px solid var(--border-color);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}
        .main-nav .container {{ display: flex; justify-content: space-between; align-items: center; height: 100%; padding: 0 20px; }}
        .main-nav .logo {{ font-size: 1.5em; font-weight: 700; color: #f9fafb; }}
        .main-nav ul {{ list-style: none; margin: 0; padding: 0; display: flex; gap: 30px; }}
        .main-nav a {{ font-weight: 500; }}

        /* --- Overview & Example Sections --- */
        #overview p, .example-item p {{ font-size: 1.1em; max-width: 80ch; }}
        #overview h1 + h1 {{ font-size: 1.8rem; border: none; color: #e5e7eb; }}
        .example-item {{
            background-color: var(--header-bg);
            padding: 1.5rem 2rem;
            border-radius: 12px;
            margin-bottom: 2rem;
            border: 1px solid var(--border-color);
        }}

        /* --- Architecture D3 Diagram --- */
        #architecture-d3-container {{
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid var(--border-color);
            background: #fff; /* D3 diagram has its own background styling */
            box-shadow: 0 0 30px rgba(0,0,0,0.5);
        }}
        {d3_styles}

        /* --- Code Blocks --- */
        .code-container {{ position: relative; }}
        pre {{
            background-color: var(--code-bg); color: #c9d1d9;
            padding: 1.25em; border-radius: 8px;
            overflow-x: auto;
            font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
            font-size: 0.9em; border: 1px solid var(--border-color);
            white-space: pre-wrap; word-break: break-all;
        }}
        pre code {{ font-family: inherit; }}
        .copy-btn {{
            position: absolute; top: 12px; right: 12px;
            background-color: #374151; color: #d1d5db;
            border: 1px solid #4b5563; border-radius: 6px;
            padding: 6px 12px; cursor: pointer; opacity: 0.3;
            transition: all 0.2s ease-in-out;
        }}
        .code-container:hover .copy-btn {{ opacity: 1; }}
        .copy-btn:hover {{ background-color: #4b5563; }}
        .copy-btn.copied {{ background-color: #22c55e; color: white; }}
        pre .c1{{color:#8b949e}} pre .k{{color:#ff7b72}} pre .kn{{color:#ff7b72}} pre .o{{color:#ff7b72}} 
        pre .bp{{color:#c9d1d9}} pre .p{{color:#c9d1d9}} pre .mi{{color:#79c0ff}} pre .nc{{color:#f0a3ff}} 
        pre .nf{{color:#d2a8ff}} pre .nn{{color:#d2a8ff}} pre .s2{{color:#a5d6ff}}

        /* --- API Reference --- */
        #api-reference-layout {{ display: flex; gap: 2rem; align-items: flex-start; }}
        #api-nav-aside {{
            position: sticky; top: calc(var(--nav-height) + 20px);
            width: 280px; flex-shrink: 0;
            height: calc(100vh - var(--nav-height) - 40px);
            overflow-y: auto; padding-right: 1.5rem;
        }}
        #api-nav-aside h3 {{ margin-top: 0; }}
        #api-nav-aside ul {{ list-style: none; padding: 0; margin: 0; }}
        #api-nav-aside li a {{ display: block; padding: 8px 12px; border-radius: 6px; font-size: 0.9em; word-break: break-all; }}
        #api-nav-aside li a:hover {{ background-color: var(--header-bg); text-decoration: none; }}
        #api-content {{ flex-grow: 1; min-width: 0; }}
        .api-file-section {{ margin-bottom: 3rem; }}
        .api-filepath {{ font-family: monospace; color: #9ca3af; border-bottom: 1px dashed var(--border-color); padding-bottom: 0.5rem; word-break: break-all; }}
        .api-element {{ background-color: var(--header-bg); border: 1px solid var(--border-color); border-radius: 12px; margin-bottom: 1.5rem; overflow: hidden; }}
        .api-element-header {{ background-color: rgba(55, 65, 81, 0.5); padding: 12px 20px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; }}
        .api-element-header h4 {{ margin: 0; font-size: 1.15em; }}
        .api-element-name {{ font-family: monospace; color: #f9fafb; }}
        .api-element-type {{ background-color: var(--accent-color); color: var(--bg-color); font-size: 0.7em; padding: 3px 8px; border-radius: 12px; margin-left: 10px; font-weight: 700; text-transform: uppercase; vertical-align: middle; }}
        .api-element-location {{ font-family: monospace; font-size: 0.85em; color: #9ca3af; }}
        .api-element-body {{ padding: 20px; }}
        .api-element-body blockquote {{ margin: 0 0 1em 0; padding: 1em; background-color: var(--code-bg); border-left: 4px solid var(--accent-color); border-radius: 0 4px 4px 0; white-space: pre-wrap; }}

        @media (max-width: 1024px) {{
            #api-reference-layout {{ flex-direction: column; }}
            #api-nav-aside {{ position: static; width: 100%; height: auto; max-height: 300px; border-right: none; border-bottom: 1px solid var(--border-color); padding-bottom: 1rem; margin-bottom: 2rem; }}
        }}
        @media (max-width: 768px) {{
            .main-nav .container {{ flex-direction: column; gap: 10px; }}
            .main-nav {{ height: auto; padding: 10px 0; }}
            body {{ font-size: 14px; }}
        }}
    </style>
</head>
<body>
    <nav class="main-nav">
        <div class="container">
            <div class="logo">🎬 Manim Library</div>
            <ul>
                <li><a href="#overview">Overview</a></li>
                <li><a href="#architecture">Architecture</a></li>
                <li><a href="#examples">Examples</a></li>
                <li><a href="#api-reference">API Reference</a></li>
            </ul>
        </div>
    </nav>
    
    <main class="container">
        <section id="overview">
            {summary_html}
        </section>

        <section id="architecture">
            <h2>Interactive Architecture Diagram</h2>
            <p>This is an interactive visualization of the Manim library's structure. Click on nodes to expand or collapse them. Hover over a node to see a summary of its purpose. You can also zoom and pan the diagram.</p>
            <div id="architecture-d3-container">
                {d3_divs}
            </div>
        </section>

        <section id="examples">
            <h2>Code Examples</h2>
            <p>Explore these functional examples to understand how to use Manim for various animation tasks.</p>
            {examples_html}
        </section>

        <section id="api-reference">
            <h2>API Reference</h2>
            <p>Detailed documentation for the modules, classes, and functions in the Manim library.</p>
            <div id="api-reference-layout">
                <aside id="api-nav-aside">
                    <h3>Modules</h3>
                    {api_nav_html}
                </aside>
                <div id="api-content">
                    {api_content_html}
                </div>
            </div>
        </section>
    </main>
    
    <script>
        // --- D3 Diagram Script ---
        (() => {{
            try {{
                {d3_script}
            }} catch (e) {{
                console.error("Error executing D3 script:", e);
                const container = document.getElementById('tree-container');
                if(container) container.innerHTML = '<p style="color:red; text-align:center;">Failed to render architecture diagram.</p>';
            }}
        }})();
        
        // --- Copy Code Button Functionality ---
        function copyCode(button) {{
            const codeContainer = button.closest('.code-container');
            const pre = codeContainer.querySelector('pre');
            const code = pre.querySelector('code');
            const textToCopy = code.innerText;
            
            navigator.clipboard.writeText(textToCopy).then(() => {{
                button.textContent = 'Copied!';
                button.classList.add('copied');
                setTimeout(() => {{
                    button.textContent = 'Copy';
                    button.classList.remove('copied');
                }}, 2000);
            }}).catch(err => {{
                console.error('Failed to copy text: ', err);
                button.textContent = 'Error';
            }});
        }}
    </script>
</body>
</html>
"""
    return final_html


# ==============================================================================
# 3. FILE WRITING ORCHESTRATOR
# THIS IS THE NEW, CORRECTED FUNCTION TO CALL
# ==============================================================================

def create_documentation_file(
    analysis_result: AnalysisResult,
    all_elements_with_docs: List[CodeElement],
    output_dir: str = "output"
):
    """
    Orchestrates the generation and saving of the documentation file.

    Args:
        analysis_result: The analysis result object.
        all_elements_with_docs: A list of all documented code elements.
        output_dir: The directory where the final HTML file will be saved.
    """
    print("Starting documentation generation...")

    # Define the output path
    output_path = Path(output_dir) / "documentation.html"

    # Ensure the output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Ensured output directory exists at: ./{output_dir}")

    # Generate the HTML content by calling the pure function
    html_content = generate_static_site(analysis_result, all_elements_with_docs)
    print("HTML content generated successfully.")

    # Write the content to the file
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✅ Successfully wrote documentation to: {output_path.resolve()}")
    except IOError as e:
        print(f"❌ Error writing to file: {e}")