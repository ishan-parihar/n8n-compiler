"""File system watcher for live compilation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Timer
from typing import Callable, Optional

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileModifiedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
)

from n8n_compiler.operations.sync import sync_workflow, SyncDirection, SyncResult
from n8n_compiler.output.terminal import console
from n8n_compiler.output.errors import (
    CompilerError,
    display_error,
    create_json_error,
)


class DebouncedHandler(FileSystemEventHandler):
    """File system event handler with debouncing."""
    
    def __init__(
        self,
        callback: Callable[[Path], None],
        debounce_ms: int = 300,
        ignore_patterns: Optional[list[str]] = None,
    ):
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_ms / 1000
        self.ignore_patterns = ignore_patterns or [".git", "__pycache__", ".n8nc/cache"]
        self._timers: dict[Path, Timer] = {}
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        path_str = str(path)
        for pattern in self.ignore_patterns:
            if pattern in path_str:
                return True
        return False
    
    def _handle_event(self, event) -> None:
        """Handle file system event with debouncing."""
        if event.is_directory:
            return
        
        path = Path(event.src_path)
        
        # Only handle JSON files
        if path.suffix != ".json":
            return
        
        if self._should_ignore(path):
            return
        
        # Cancel existing timer for this path
        if path in self._timers:
            self._timers[path].cancel()
        
        # Set new timer
        timer = Timer(self.debounce_seconds, self.callback, args=[path])
        self._timers[path] = timer
        timer.start()
    
    def on_modified(self, event: FileModifiedEvent) -> None:
        self._handle_event(event)
    
    def on_created(self, event: FileCreatedEvent) -> None:
        self._handle_event(event)


class Watcher:
    """Watches workflow files and auto-syncs on changes."""
    
    def __init__(
        self,
        watch_path: Path,
        debounce_ms: int = 300,
    ):
        self.watch_path = Path(watch_path).resolve()
        self.debounce_ms = debounce_ms
        self.observer = Observer()
        self._running = False
        
        # Determine what we're watching
        if self.watch_path.is_file() and self.watch_path.suffix == ".json":
            self.workflow_json = self.watch_path
            self.workflow_dir = self.watch_path.parent / self.watch_path.stem
        elif self.watch_path.is_dir():
            self.workflow_dir = self.watch_path
            manifest_path = self.watch_path / "manifest.json"
            if manifest_path.exists():
                from n8n_compiler.core.models import Manifest
                manifest = Manifest.load(manifest_path)
                source = manifest.meta.source_file
                if source.startswith("../"):
                    self.workflow_json = self.watch_path.parent / source[3:]
                else:
                    self.workflow_json = None
            else:
                self.workflow_json = None
        else:
            raise ValueError(f"Invalid watch path: {watch_path}")
    
    def _on_file_change(self, changed_path: Path) -> None:
        """Handle file change event."""
        try:
            # Determine what changed
            relative = changed_path.relative_to(self.watch_path.parent)
            console.change_detected(str(relative))
            
            # Perform sync
            result = sync_workflow(self.watch_path)
            
            if result.error:
                console.error(result.error)
            elif result.direction == SyncDirection.NONE:
                console.info(result.message)
            else:
                console.sync_result(
                    direction=result.direction.value,
                    source=str(result.source_path.name),
                    target=str(result.target_path.name),
                    nodes=result.nodes_affected,
                    connections=result.nodes_affected,  # Approximation
                )
                
        except json.JSONDecodeError as e:
            error = create_json_error(changed_path, e)
            display_error(error)
        except Exception as e:
            console.error(str(e))
    
    def start(self) -> None:
        """Start watching for changes."""
        self._running = True
        
        handler = DebouncedHandler(
            callback=self._on_file_change,
            debounce_ms=self.debounce_ms,
        )
        
        # Watch the directory
        watch_target = self.workflow_dir if self.workflow_dir.exists() else self.watch_path.parent
        self.observer.schedule(handler, str(watch_target), recursive=True)
        
        # Also watch the JSON file's parent if different
        if self.workflow_json and self.workflow_json.parent != watch_target:
            self.observer.schedule(handler, str(self.workflow_json.parent), recursive=False)
        
        self.observer.start()
        
        console.header(watching=str(self.watch_path))
        console.info("Watching for changes... (Ctrl+C to stop)")
        
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        self.observer.stop()
        self.observer.join()
        console.info("Stopped watching")


def watch_workflow(
    path: Path,
    debounce_ms: int = 300,
) -> None:
    """
    Watch a workflow for changes and auto-sync.
    
    Args:
        path: Path to workflow JSON or directory
        debounce_ms: Debounce time in milliseconds
    """
    watcher = Watcher(path, debounce_ms)
    watcher.start()
