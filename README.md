# 🤖 ConductDoc: AI-Powered Python Documentation Generator

**Project for: ConductAI AI Engineer Take-Home**

---

## 🚀 Project Overview

ConductDoc is a prototype system that automatically generates comprehensive, human-friendly documentation for any Python library. It was built to solve the specific pain points of a notional customer: a small IT team, proficient in scripting but new to Python, tasked with leveraging the `manim` library for educational video production.

The system addresses their needs by:
1.  **Crawling** a Python repository to understand its structure.
2.  **Analyzing** the code and existing docs using AI (currently mocked) to synthesize insights.
3.  **Generating** a multi-page static HTML site with:
    *   A high-level summary for stakeholders.
    *   An interactive architecture diagram.
    *   Navigable, step-by-step explanations of every class and function.
    *   Curated code examples for common tasks.

This prototype was built in under 4 hours and focuses on demonstrating a robust, scalable architecture and a deep understanding of the user's core problems.

### ✨ Key Features & Design Philosophy

*   **Code is Truth:** The primary source for documentation is the code itself, ensuring accuracy even when official docs are stale.
*   **Context is King:** The system intelligently uses the `README.md` and existing `docs/` folders as context to make the AI-generated content richer and more aligned with the library's intent.
*   **User-Centric by Design:** The output is specifically tailored for developers who are unfamiliar with Python's idioms, providing simple, step-by-step explanations rather than just API signatures.
*   **Developer-Friendly CLI:** A clean command-line interface with smart auto-detection and powerful manual overrides for a great user experience.
*   **Clean & Scalable Architecture:** The code is structured as a proper Python package (`conductdoc/`) with a clear separation of concerns (crawling, analyzing, generating), making it easy to maintain, test, and extend.

---

## ⚡️ Quick Start

**3. Run the generator:**

The script will automatically clone the manim repository into a temporary directory, run the full pipeline, and generate the documentation in a generated_docs/ folder.

```bash
python main.py --repo-url https://github.com/ManimCommunity/manim.git
```

**4. View the output:**

Open the main page in your browser to explore the generated site.

```bash
open generated_docs/index.html
```

## ⚙️ Advanced Usage

You can override the auto-detection for the source and documentation directories:

```bash
python main.py \
    --repo-url https://github.com/ManimCommunity/manim.git \
    --src-dir manimlib \
    --docs-dir docs/source
```

## 🧠 Design Decisions & Trade-offs

As this was a time-limited exercise, I made several strategic decisions to prioritize a strong foundation over feature completeness.

| Decision | Rationale & Trade-offs | What I'd Do With More Time |
|----------|------------------------|----------------------------|
| Mocked AI & Templating | The core challenge is the system's architecture and data flow, not the specific prompts or HTML styling. Mocking these external dependencies allowed me to focus 100% on building a robust, testable pipeline. The current mocked functions return placeholder data that proves the end-to-end flow works correctly. | Integrate Real Services: I would implement the analyzer.py module with the openai library (using GPT-4 for its strong reasoning) and the generator.py module with Jinja2 for powerful and maintainable HTML templating. |
| Standard Library Focus | The crawler uses only the standard ast, subprocess, pathlib, and tempfile modules. This ensures the prototype runs anywhere without dependencies and demonstrates a solid command of Python's built-in tools. | Add Specialized Libraries: I would add docutils to properly parse .rst files in the docs folder for richer context, and requests or a dedicated library for any web-crawling features. |
| Static Site Output | A static HTML site is a perfect deliverable for the customer's request for a "manual". It's fast, portable, and requires no backend server to view. | Build a Web Application: For a V2, I would build a simple Flask or FastAPI web application where a user could input a Git URL and see the documentation being generated in real-time. |
| No Persistent State | The system clones the repo into a temporary directory and leaves no trace. This is clean and simple for a CLI tool. | Add Caching: For performance, I would implement a caching layer (e.g., using joblib or a simple file-based cache) to store the AST parsing results and even AI outputs, so that re-running the tool on an unchanged repository is instantaneous. |

## 🔮 Future Improvements & Vision

This prototype is a solid foundation. Here's how I would evolve it into a full-fledged product:

**Semantic Search:** Integrate a vector database (like ChromaDB or Pinecone) to allow users to ask natural language questions ("How do I render a chart?") and get back the most relevant code examples and documentation sections.

**Inconsistency Detection:** Use the AI to compare the generated documentation (from the code) with the existing documentation (from the docs folder) and automatically flag potential "documentation rot" where the docs are out of sync with the code's behavior.

**Interactive Examples:** Generate examples that can be run and modified directly in the browser using tools like Pyodide.

**VS Code Extension:** Create an extension that brings the AI-generated explanations directly into the developer's editor, appearing as enhanced tooltips on hover.

**CI/CD Integration:** Package the tool as a GitHub Action that automatically re-generates and publishes the documentation on every push to the main branch.

Thank you for the opportunity to work on this exciting project!