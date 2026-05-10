"""Unpack operation - converts workflow JSON to directory structure."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from n8n_compiler.core.models import (
    Manifest,
    Node,
    NodeCategory,
    NodeManifestEntry,
    SyncInfo,
    Workflow,
    WorkflowMeta,
    WorkflowSettings,
    compute_file_hash,
    compute_hash,
)


def unpack_workflow(
    source_json: Path,
    output_dir: Optional[Path] = None,
    force: bool = False,
) -> Path:
    """
    Unpack a workflow JSON file into a directory structure.
    
    Args:
        source_json: Path to the workflow JSON file
        output_dir: Optional output directory (defaults to same name as JSON)
        force: If True, overwrite existing directory
        
    Returns:
        Path to the created directory
    """
    source_json = Path(source_json).resolve()
    
    if not source_json.exists():
        raise FileNotFoundError(f"Source file not found: {source_json}")
    
    # Determine output directory
    if output_dir is None:
        output_dir = source_json.parent / source_json.stem
    else:
        output_dir = Path(output_dir).resolve()
    
    # Check if directory exists
    if output_dir.exists() and not force:
        manifest_path = output_dir / "manifest.json"
        if manifest_path.exists():
            # Directory already unpacked, check if we should update
            pass
    
    # Create directory structure
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_dir = output_dir / "nodes"
    nodes_dir.mkdir(exist_ok=True)
    
    # Create category subdirectories
    for category in NodeCategory:
        (nodes_dir / category.value).mkdir(exist_ok=True)
    
    # Load workflow
    workflow = Workflow.load(source_json)
    
    # Sort nodes topologically
    sorted_nodes = workflow.topological_sort()
    
    # Create manifest
    now = datetime.now().astimezone().isoformat()
    json_hash = compute_file_hash(source_json)
    json_mtime = datetime.fromtimestamp(source_json.stat().st_mtime).astimezone().isoformat()
    
    manifest = Manifest(
        meta=WorkflowMeta(
            name=source_json.stem,
            description=f"Unpacked from {source_json.name}",
            source_file=f"../{source_json.name}",
            created_at=now,
            last_synced=now,
        ),
        sync=SyncInfo(
            mode="auto",
            json_hash=json_hash,
            json_mtime=json_mtime,
        ),
        workflow_settings=WorkflowSettings(
            name=workflow.name,
            settings=workflow.settings,
            staticData=workflow.staticData,
            pinData=workflow.pinData,
        ),
    )
    
    # Track filenames to avoid duplicates
    used_filenames: dict[str, int] = {}
    
    # Extract instance ID from source workflow if available
    with open(source_json, "r", encoding="utf-8") as f:
        raw_workflow = json.load(f)
    instance_id = raw_workflow.get("meta", {}).get(
        "instanceId", 
        "generated-" + compute_hash(str(source_json))[-16:]
    )
    
    # Track nodes per category for README generation
    category_nodes: dict[NodeCategory, list[tuple[int, str, str]]] = {
        cat: [] for cat in NodeCategory
    }
    
    # Write individual node files in clipboard-compatible format
    for order, node in enumerate(sorted_nodes, start=1):
        category = node.get_category()
        
        # Add execution order prefix for LLM-friendly ordering
        base_filename = f"{order:03d}_{node.get_safe_filename()}"
        
        # Handle duplicate filenames (rare with order prefix)
        if base_filename in used_filenames:
            used_filenames[base_filename] += 1
            name_part = base_filename.rsplit(".", 1)[0]
            base_filename = f"{name_part}_{used_filenames[base_filename]}.json"
        else:
            used_filenames[base_filename] = 1
        
        # Track for README
        category_nodes[category].append((order, base_filename, node.name))
        
        # Get outgoing connections for this node (name-based for n8n compatibility)
        node_connections = {}
        if node.name in workflow.connections:
            node_connections[node.name] = workflow.connections[node.name]
        
        # Get pinData for this node if exists
        node_pin_data = {}
        if workflow.pinData and node.name in workflow.pinData:
            node_pin_data[node.name] = workflow.pinData[node.name]
        
        # Build clipboard-compatible node file
        clipboard_data = {
            "nodes": [node.to_file_dict()],
            "connections": node_connections,
            "pinData": node_pin_data,
            "meta": {"instanceId": instance_id}
        }
        
        # Write node file
        node_path = nodes_dir / category.value / base_filename
        
        with open(node_path, "w", encoding="utf-8") as f:
            json.dump(clipboard_data, f, indent=2, ensure_ascii=False)
        
        # Compute hash
        node_hash = compute_hash(json.dumps(clipboard_data, sort_keys=True))
        
        # Add to manifest
        relative_path = f"nodes/{category.value}/{base_filename}"
        manifest.nodes[node.id] = NodeManifestEntry(
            name=node.name,
            file=relative_path,
            type=node.type,
            category=category,
            hash=node_hash,
            execution_order=order,
        )
    
    # Store connections in manifest (transform from name-based to ID-based)
    # First, create name-to-id mapping
    name_to_id = {node.name: node.id for node in workflow.nodes}
    
    # Transform connections to use node IDs
    for source_name, outputs in workflow.connections.items():
        source_id = name_to_id.get(source_name)
        if not source_id:
            continue
            
        manifest.connections[source_id] = {}
        
        for output_type, branches in outputs.items():
            manifest.connections[source_id][output_type] = []
            
            for branch in branches:
                new_branch = []
                for target in branch:
                    target_name = target.get("node")
                    target_id = name_to_id.get(target_name)
                    if target_id:
                        new_branch.append({
                            "node_id": target_id,
                            "type": target.get("type", "main"),
                            "index": target.get("index", 0),
                        })
                manifest.connections[source_id][output_type].append(new_branch)
    
    # Compute directory hash
    dir_hash = compute_hash(
        json.dumps(
            {node_id: entry.hash for node_id, entry in manifest.nodes.items()},
            sort_keys=True
        )
    )
    manifest.sync.dir_hash = dir_hash
    manifest.sync.dir_mtime = now
    
    # Save manifest
    manifest.save(output_dir / "manifest.json")
    
    # Generate Mermaid graph
    generate_mermaid_graph(manifest, output_dir / "graph.mmd")
    
    # Generate category READMEs for LLM navigation
    generate_category_readmes(nodes_dir, category_nodes)
    
    return output_dir


def generate_mermaid_graph(manifest: Manifest, output_path: Path) -> None:
    """Generate a Mermaid flowchart from the manifest."""
    lines = ["flowchart LR"]
    
    # Create node definitions with short IDs
    id_to_short = {}
    for i, (node_id, entry) in enumerate(
        sorted(manifest.nodes.items(), key=lambda x: x[1].execution_order)
    ):
        short_id = f"N{i+1}"
        id_to_short[node_id] = short_id
        
        # Escape quotes in name
        safe_name = entry.name.replace('"', "'")
        
        # Use different shapes for different categories
        if entry.category == NodeCategory.TRIGGERS:
            lines.append(f'    {short_id}[("{safe_name}")]')
        elif entry.category == NodeCategory.ROUTING:
            lines.append(f'    {short_id}{{"{safe_name}"}}')
        elif entry.category == NodeCategory.AI:
            lines.append(f'    {short_id}[["{safe_name}"]]')
        else:
            lines.append(f'    {short_id}["{safe_name}"]')
    
    lines.append("")
    
    # Create connections
    for source_id, outputs in manifest.connections.items():
        source_short = id_to_short.get(source_id)
        if not source_short:
            continue
            
        for output_type, branches in outputs.items():
            for branch in branches:
                for target in branch:
                    target_id = target.get("node_id")
                    target_short = id_to_short.get(target_id)
                    if target_short:
                        if output_type == "main":
                            lines.append(f"    {source_short} --> {target_short}")
                        else:
                            # AI connections use dotted lines
                            lines.append(f"    {source_short} -.->|{output_type}| {target_short}")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_category_readmes(
    nodes_dir: Path,
    category_nodes: dict[NodeCategory, list[tuple[int, str, str]]],
) -> None:
    """Generate README.md in each category directory for LLM navigation."""
    for category, nodes in category_nodes.items():
        if not nodes:
            continue
        
        category_dir = nodes_dir / category.value
        readme_path = category_dir / "README.md"
        
        lines = [
            f"# {category.value.title()} ({len(nodes)} nodes)",
            "",
            "| Order | File | Node Name |",
            "|-------|------|-----------|",
        ]
        
        for order, filename, name in sorted(nodes, key=lambda x: x[0]):
            lines.append(f"| {order} | {filename} | {name} |")
        
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

