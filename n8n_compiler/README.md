# n8n Workflow Compiler

A bidirectional Python compiler for n8n workflow JSON files.

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Initialize workspace
n8nc init

# Unpack a workflow
n8nc unpack workflow.json

# Pack a directory
n8nc pack workflow_dir/

# Smart sync
n8nc sync workflow_dir/

# Watch mode
n8nc watch .
```
