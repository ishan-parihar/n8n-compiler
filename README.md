# n8n-compiler 🚀

**Treat your n8n workflows as code.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-005571.svg)](https://docs.pydantic.dev/)
[![n8n](https://img.shields.io/badge/n8n-workflows-ff6d5a.svg)](https://n8n.io/)
[![CLI](https://img.shields.io/badge/CLI-click-0073B8.svg)](https://click.palletsprojects.com/)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC.svg)](https://docs.pytest.org/)

`n8n-compiler` (CLI: `n8nc`) is a high-performance bidirectional compiler that transforms opaque n8n workflow JSON blobs into modular, version-controlled Python directory structures—and back again.

By moving the "Source of Truth" from a browser-based GUI to a local filesystem, it enables a professional software engineering workflow for automation.

---

## 🚩 The Problem: The "JSON Blob" Trap

n8n is a powerful tool, but for complex, production-grade workflows, the JSON format becomes a bottleneck:
- **Opaque Diffs**: A small change in the GUI results in massive, unreadable changes in the JSON.
- **No Version Control**: You cannot effectively use Git to branch, merge, or peer-review structural changes in a 5,000-line JSON file.
- **Fragile Management**: Manual backups of `.json` files are not a substitute for a structured codebase.
- **Lack of Type Safety**: There is no compile-time validation that a node's configuration is structurally sound before importing it into n8n.

## 💡 The Solution: Code-First Automation

`n8n-compiler` breaks this cycle by introducing a **Compilation Layer**. 

### The Bidirectional Pipeline
`n8n Workflow JSON` $\xrightarrow{\text{unpack}}$ `Modular Directory` $\xrightarrow{\text{pack}}$ `n8n Workflow JSON`

1. **Unpack**: Decompiles the JSON into a human-readable directory tree. Each node and connection becomes a discrete file.
2. **Edit**: Use your favorite IDE (VS Code, Cursor, PyCharm) to edit workflows with full search-and-replace, linting, and Git tracking.
3. **Pack**: Recompiles the directory back into a valid n8n JSON, ensuring the structural integrity of the workflow via strict schema validation.

---

## ✨ Key Capabilities

### 🛠 Core Tooling
- **`n8nc unpack`**: Transforms JSON $\to$ Directory. Organizes nodes by type (AI, Integrations, Processors, Routing, Triggers).
- **`n8nc pack`**: Transforms Directory $\to$ JSON. Validates the manifest and ensures the graph is reconstructible.
- **`n8nc sync`**: A smart synchronization engine that detects the most recent change (JSON or Directory) and updates the other side automatically.
- **`n8nc watch`**: A real-time filesystem observer. Save a file in your IDE $\to$ `n8nc` instantly recompiles the JSON.
- **`n8nc validate`**: Uses Pydantic v2 to enforce strict type-safety on workflow models, catching errors before they reach the n8n engine.

### 🏗 Engineering Rigor
- **Type-Safe Models**: Every node and connection is backed by a Pydantic model, ensuring that the compiled output always adheres to n8n's internal expectations.
- **Manifest-Driven**: Uses a `manifest.json` to preserve the precise execution order and topological sorting of the workflow.
- **Rich CLI Experience**: Built with `Click` and `Rich` for professional terminal output, including progress bars, formatted tables, and clear error reporting.

---

## 🌌 Potentialities & Possibilities

This compiler isn't just a utility; it's a foundation for **Automation Engineering**:

### 1. GitOps for Workflows
Imagine a CI/CD pipeline where:
- A developer proposes a workflow change via a **Pull Request**.
- The CI runs `n8nc validate` to ensure the change doesn't break the workflow structure.
- Upon merge, the compiled JSON is automatically pushed to the n8n API via a webhook.

### 2. Composable Automation (Fragments)
Because workflows are now directories, you can create **Workflow Libraries**. Instead of duplicating complex logic, you can symlink or copy "fragment" directories (e.g., a standardized "Error Handling" block) across multiple projects.

### 3. Generative AI Integration
LLMs are significantly better at generating structured directory trees and small individual files than they are at generating 10,000-line JSON blobs. 
- **Prompt $\to$ Directory $\to$ JSON**: You can prompt an AI to "Add a Notion-to-Slack routing node to the project," and it only needs to write one small file in the `nodes/` folder.

### 4. Programmatic Workflow Generation
Build workflows using Python scripts. Instead of manual GUI clicking, write a script that generates the directory structure based on a config file, then compile it.

---

## 🚀 Quick Start

### Installation
```bash
git clone https://github.com/ishan-parihar/n8n-compiler.git
cd n8n-compiler
pip install -e .
```

### Usage Example
```bash
# 1. Decompile an existing workflow
n8nc unpack my_workflow.json -o my_project/

# 2. Edit files in my_project/ using your IDE (Git commit your changes!)

# 3. Recompile back to JSON
n8nc pack my_project/ -o my_workflow_updated.json

# 4. Start a watch session for rapid iteration
n8nc watch my_project/
```

## 🛠 Tech Stack
- **Language**: Python 3.10+
- **Validation**: Pydantic v2 (Strict Type Safety)
- **CLI Framework**: Click
- **UI/UX**: Rich (Terminal formatting)
- **Event Loop**: Watchdog (Filesystem monitoring)
- **Testing**: Pytest

---
Developed by [Ishan Parihar](https://github.com/ishan-parihar) as part of a larger pursuit of scalable, engineered automation.

If you find this project useful, [consider supporting its development](https://rzp.io/rzp/ishan-parihar)
