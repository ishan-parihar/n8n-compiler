"""CLI interface for n8nc - n8n Workflow Compiler."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from n8n_compiler import __version__
from n8n_compiler.core.models import Manifest, WorkspaceConfig
from n8n_compiler.operations import (
    unpack_workflow,
    pack_workflow,
    sync_workflow,
    SyncDirection,
)
from n8n_compiler.operations.pack import validate_directory
from n8n_compiler.output.terminal import console
from n8n_compiler.output.errors import display_error, CompilerError


@click.group()
@click.version_option(version=__version__, prog_name="n8nc")
def cli():
    """n8nc - n8n Workflow Compiler
    
    Bidirectional sync between n8n workflow JSON files and modular directories.
    """
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True), default=".")
def init(path: str):
    """Initialize n8nc workspace in the current directory."""
    workspace_path = Path(path).resolve()
    config_dir = workspace_path / ".n8nc"
    config_file = config_dir / "config.json"
    
    if config_file.exists():
        console.warning(f"Workspace already initialized at {workspace_path}")
        return
    
    # Create config
    config = WorkspaceConfig()
    
    # Find existing JSON workflows
    for json_file in workspace_path.glob("*.json"):
        if json_file.name.startswith("."):
            continue
        config.workflows.append({
            "name": json_file.stem,
            "source": json_file.name,
            "directory": f"{json_file.stem}/",
            "sync_mode": "auto",
        })
    
    config.save(config_file)
    
    console.success(f"Initialized workspace at {workspace_path}")
    console.info(f"Found {len(config.workflows)} workflow(s)")
    
    for wf in config.workflows:
        console.info(f"  • {wf['name']}")


@cli.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), help="Output directory path")
@click.option("-f", "--force", is_flag=True, help="Overwrite existing directory")
def unpack(source: str, output: Optional[str], force: bool):
    """Unpack a workflow JSON into a directory structure.
    
    SOURCE: Path to the n8n workflow JSON file
    """
    source_path = Path(source).resolve()
    output_path = Path(output).resolve() if output else None
    
    try:
        result_dir = unpack_workflow(source_path, output_path, force)
        
        # Load manifest for summary
        manifest = Manifest.load(result_dir / "manifest.json")
        
        # Count by category
        categories = {}
        for entry in manifest.nodes.values():
            cat = entry.category.value
            categories[cat] = categories.get(cat, 0) + 1
        
        console.success(f"Unpacked to {result_dir}")
        console.workflow_summary(
            name=manifest.meta.name,
            nodes=len(manifest.nodes),
            connections=sum(
                len(branches)
                for outputs in manifest.connections.values()
                for branches in outputs.values()
            ),
            categories=categories,
        )
        
    except Exception as e:
        console.error(str(e))
        raise click.Abort()


@cli.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), help="Output JSON file path")
@click.option("-f", "--force", is_flag=True, help="Overwrite existing JSON")
def pack(source: str, output: Optional[str], force: bool):
    """Pack a directory structure into a workflow JSON.
    
    SOURCE: Path to the unpacked workflow directory
    """
    source_path = Path(source).resolve()
    output_path = Path(output).resolve() if output else None
    
    # Validate first
    errors = validate_directory(source_path)
    if errors:
        for err in errors:
            console.error(err)
        raise click.Abort()
    
    try:
        result_json = pack_workflow(source_path, output_path, force)
        manifest = Manifest.load(source_path / "manifest.json")
        
        console.success(f"Packed to {result_json}")
        console.info(f"  Nodes: {len(manifest.nodes)}")
        
    except Exception as e:
        console.error(str(e))
        raise click.Abort()


@cli.command("pack-auto")
@click.argument("source", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), help="Output JSON file path")
def pack_auto_cmd(source: str, output: Optional[str]):
    """Pack workflow from node files alone (no manifest required).
    
    Uses filename order prefixes (001_, 002_) to determine execution order.
    
    SOURCE: Path to the unpacked workflow directory
    """
    from n8n_compiler.operations.pack import pack_auto
    
    source_path = Path(source).resolve()
    output_path = Path(output).resolve() if output else None
    
    try:
        result_json = pack_auto(source_path, output_path)
        
        # Count nodes by scanning files
        nodes_dir = source_path / "nodes"
        node_count = len(list(nodes_dir.glob("**/*.json")))
        
        console.success(f"Packed to {result_json}")
        console.info(f"  Nodes: {node_count} (manifest-free)")
        
    except Exception as e:
        console.error(str(e))
        raise click.Abort()


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--force-json", is_flag=True, help="Force sync from JSON to directory")
@click.option("--force-dir", is_flag=True, help="Force sync from directory to JSON")
def sync(path: str, force_json: bool, force_dir: bool):
    """Smart sync between JSON and directory.
    
    PATH: Path to either the workflow JSON or directory
    """
    workflow_path = Path(path).resolve()
    
    # Determine forced direction
    force_direction = None
    if force_json:
        force_direction = SyncDirection.JSON_TO_DIR
    elif force_dir:
        force_direction = SyncDirection.DIR_TO_JSON
    
    try:
        result = sync_workflow(workflow_path, force_direction)
        
        if result.error:
            console.error(result.message)
            console.error(result.error)
            raise click.Abort()
        
        if result.direction == SyncDirection.NONE:
            console.success(result.message)
        else:
            console.sync_result(
                direction=result.direction.value,
                source=str(result.source_path.name),
                target=str(result.target_path.name),
                nodes=result.nodes_affected,
                connections=result.nodes_affected,
            )
            
    except click.Abort:
        raise
    except Exception as e:
        console.error(str(e))
        raise click.Abort()


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--debounce", type=int, default=300, help="Debounce time in ms")
def watch(path: str, debounce: int):
    """Watch for changes and auto-sync.
    
    PATH: Path to workflow JSON, directory, or workspace root
    """
    from n8n_compiler.watch import watch_workflow
    
    workflow_path = Path(path).resolve()
    
    try:
        watch_workflow(workflow_path, debounce)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.error(str(e))
        raise click.Abort()


@cli.command()
@click.argument("path", type=click.Path(exists=True))
def validate(path: str):
    """Validate a workflow directory structure.
    
    PATH: Path to the unpacked workflow directory
    """
    source_path = Path(path).resolve()
    
    if not source_path.is_dir():
        console.error("Path must be a directory")
        raise click.Abort()
    
    errors = validate_directory(source_path)
    
    if errors:
        console.error(f"Found {len(errors)} error(s):")
        for err in errors:
            console.error(f"  • {err}")
        raise click.Abort()
    else:
        console.success("Validation passed ✓")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
def graph(path: str):
    """Display the workflow graph.
    
    PATH: Path to workflow JSON or directory
    """
    workflow_path = Path(path).resolve()
    
    # Find the mermaid file
    if workflow_path.is_file():
        graph_path = workflow_path.parent / workflow_path.stem / "graph.mmd"
    else:
        graph_path = workflow_path / "graph.mmd"
    
    if not graph_path.exists():
        console.error(f"Graph file not found: {graph_path}")
        console.info("Run 'n8nc unpack' first to generate the graph")
        raise click.Abort()
    
    # Display the graph content
    with open(graph_path) as f:
        content = f.read()
    
    console.console.print()
    console.console.print(f"[bold]Workflow Graph[/bold] ({graph_path.name})")
    console.console.print()
    console.console.print(content)


if __name__ == "__main__":
    cli()
