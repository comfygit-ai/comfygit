# CLI Refactoring Plan - DRY Principles & Code Quality

## Executive Summary

This plan addresses significant code duplication across the CLI package, focusing on making the codebase more maintainable, testable, and consistent. The refactoring follows the project's "simple, elegant, maintainable" philosophy and avoids over-engineering.

**Estimated Impact**: ~500-700 lines of code reduction across 5 files
**Risk Level**: Low to Medium (incremental approach minimizes risk)
**Priority**: High (foundational improvements benefit all future CLI development)

---

## Current State Analysis

### Files Analyzed
- `packages/cli/comfydock_cli/env_commands.py` (1322 lines)
- `packages/cli/comfydock_cli/global_commands.py` (1064 lines)
- `packages/cli/comfydock_cli/cli.py` (339 lines)
- `packages/cli/comfydock_cli/strategies/interactive.py` (830 lines)
- `packages/cli/comfydock_cli/strategies/rollback.py` (41 lines)

### Duplication Patterns Identified

#### 1. **Duplicate Choice Prompt Logic** (HIGH PRIORITY)
- **Location**: `interactive.py:28-60` (nodes) and `interactive.py:385-417` (models)
- **Duplication**: ~90% identical code, only differs in allowed special characters
- **Impact**: 60+ lines duplicated

#### 2. **Error Handling Boilerplate** (HIGH PRIORITY)
- **Pattern**:
  ```python
  try:
      # operation
  except Exception as e:
      if logger:
          logger.error(f"...: {e}", exc_info=True)
      print(f"✗ Failed: {e}", file=sys.stderr)
      sys.exit(1)
  ```
- **Occurrences**: 15+ methods across `env_commands.py` and `global_commands.py`
- **Impact**: ~150 lines of repeated code

#### 3. **Pagination/Browse Logic** (MEDIUM PRIORITY)
- **Location**: `interactive.py:332-374` (nodes) and `interactive.py:779-827` (models)
- **Duplication**: Nearly identical page navigation, input handling
- **Impact**: 90+ lines duplicated

#### 4. **Search Result Display** (MEDIUM PRIORITY)
- **Location**: `interactive.py:246-303` (nodes) and `interactive.py:641-710` (models)
- **Pattern**: Numbered lists, refinement options, selection handling
- **Impact**: 130+ lines with similar structure

#### 5. **Progress Callbacks** (MEDIUM PRIORITY)
- **Location**:
  - `env_commands.py:898-928` (node install)
  - `env_commands.py:914-928` (model download)
  - `global_commands.py:198-261` (import)
  - `global_commands.py:327-334` (export)
- **Pattern**: Inline function definitions with similar structure
- **Impact**: 120+ lines of similar callback definitions

#### 6. **Workspace Initialization** (LOW PRIORITY)
- **Location**: Both command classes
- **Pattern**: `@cached_property def workspace(self) -> Workspace`
- **Impact**: Minor duplication, but architectural improvement opportunity

#### 7. **Yes/No Confirmation** (LOW PRIORITY)
- **Locations**:
  - `env_commands.py:146` (delete)
  - `env_commands.py:887` (repair)
  - `global_commands.py:367` (export)
  - `rollback.py:23` (rollback)
- **Pattern**: `input("... (y/N): ").strip().lower()`
- **Impact**: Small but scattered across codebase

---

## Refactoring Strategy

### Guiding Principles
1. **Incremental approach** - Refactor one pattern at a time with tests
2. **No over-engineering** - Keep abstractions simple and focused
3. **Maintain UX** - Don't change user-facing behavior
4. **Test coverage** - Add tests before refactoring when missing
5. **No legacy support** - Feel free to break old patterns if cleaner

### Phase 1: Foundation (Week 1) ✅ HIGH PRIORITY

#### Task 1.1: Create Error Handling Decorator
**New File**: `packages/cli/comfydock_cli/utils/errors.py`

```python
def handle_command_error(logger_name: str = None):
    """Decorator for CLI command error handling with logging and stderr output."""
    # Captures exceptions, logs with optional logger, prints to stderr, exits 1
```

**Benefits**:
- Eliminates 150+ lines of repeated try/except blocks
- Consistent error messaging across all commands
- Easier to add error tracking/telemetry later

**Files to Modify**:
- `env_commands.py` - Apply to all command methods (~15 methods)
- `global_commands.py` - Apply to all command methods (~12 methods)

**Testing**:
- Create `tests/test_error_handler.py`
- Test success case, exception case, logger integration
- Test exit code behavior

**Implementation Notes**:
- Should preserve logger parameter from `@with_env_logging` decorator
- Must work with both workspace and environment loggers
- Consider using functools.wraps for proper decorator behavior

---

#### Task 1.2: Create Unified CLI Prompts Utility
**New File**: `packages/cli/comfydock_cli/ui/prompts.py`

```python
class CLIPrompts:
    """Unified CLI prompting utilities for user input."""

    @staticmethod
    def choice(prompt: str, options: int, special_chars: list[str] = None,
               has_browse: bool = False, default: str = "1") -> str:
        """Unified choice prompt with validation."""

    @staticmethod
    def yes_no(prompt: str, default: bool = False) -> bool:
        """Yes/no confirmation prompt."""

    @staticmethod
    def text_input(prompt: str, required: bool = True) -> str | None:
        """Free-form text input with optional requirement."""
```

**Benefits**:
- Consolidates 60+ lines of duplicate prompt logic
- Consistent input validation
- Single place to add features (e.g., ctrl-c handling, input history)

**Files to Modify**:
- `strategies/interactive.py` - Replace both `_unified_choice_prompt` methods
- `env_commands.py` - Replace yes/no confirmation patterns
- `global_commands.py` - Replace confirmation patterns

**Testing**:
- Create `tests/ui/test_prompts.py`
- Mock input() for automated testing
- Test validation, defaults, special characters

**Implementation Notes**:
- Keep simple - don't add readline/prompt_toolkit complexity yet
- Support keyboard interrupt gracefully
- Return typed values (bool for yes_no, str for choice)

---

#### Task 1.3: Create New Directory Structure
**New Directories**:
```
packages/cli/comfydock_cli/
├── ui/
│   ├── __init__.py
│   └── prompts.py (created in Task 1.2)
└── utils/
    └── errors.py (created in Task 1.1)
```

**Files to Create**:
- `packages/cli/comfydock_cli/ui/__init__.py` - Export CLIPrompts
- Update `packages/cli/comfydock_cli/utils/__init__.py` if exists

---

### Phase 2: Interactive Strategies (Week 2) 🟡 MEDIUM PRIORITY

#### Task 2.1: Abstract Browse Pagination
**New File**: `packages/cli/comfydock_cli/ui/pagination.py`

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar('T')

class BrowsePagination(Generic[T]):
    """Generic pagination for browsing lists with page navigation."""

    def __init__(self, items: list[T], page_size: int = 10):
        self.items = items
        self.page_size = page_size
        self.current_page = 0

    @abstractmethod
    def render_item(self, item: T, index: int) -> None:
        """Render a single item. Subclasses implement display logic."""

    def browse(self) -> T | None | str:
        """Browse items with pagination. Returns selected item, 'BACK', or None."""
```

**Benefits**:
- Eliminates 90+ lines of duplicate pagination logic
- Reusable for any future browseable lists
- Type-safe with generics

**Files to Modify**:
- `strategies/interactive.py` - Replace `_browse_all_packages` (lines 332-374)
- `strategies/interactive.py` - Replace `_browse_all_models` (lines 779-827)

**Testing**:
- Create `tests/ui/test_pagination.py`
- Test page navigation (next, prev, boundaries)
- Test item selection
- Test back/quit behavior

**Implementation Notes**:
- Use template method pattern for item rendering
- Keep keyboard shortcuts consistent (N/P/B/Q)
- Consider adding jump-to-page feature if useful

---

#### Task 2.2: Create Search Results Presenter
**New File**: `packages/cli/comfydock_cli/ui/search_results.py`

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar('T')

class SearchResultsPresenter(Generic[T]):
    """Base class for presenting search results with refinement options."""

    def __init__(self, max_display: int = 5):
        self.max_display = max_display

    @abstractmethod
    def render_result(self, result: T, index: int) -> None:
        """Render a single search result."""

    @abstractmethod
    def get_choice_options(self) -> list[str]:
        """Return available choice options (e.g., ['r', 'o', 's'])."""

    def present(self, results: list[T], search_term: str) -> tuple[T | None, str]:
        """Present results and get user choice. Returns (selected_item, action)."""
```

**Concrete Implementations**:
- `NodeSearchResultsPresenter` - For node search results
- `ModelSearchResultsPresenter` - For model search results

**Benefits**:
- Reduces 130+ lines of similar display logic
- Consistent search UX across node/model resolution
- Easy to add new search result types

**Files to Modify**:
- `strategies/interactive.py:246-303` - Use NodeSearchResultsPresenter
- `strategies/interactive.py:641-710` - Use ModelSearchResultsPresenter

**Testing**:
- Create `tests/ui/test_search_results.py`
- Test result display truncation
- Test choice validation
- Test refinement flow

---

### Phase 3: Command Architecture (Week 3) 🟢 ARCHITECTURAL

#### Task 3.1: Create Base Command Class
**New File**: `packages/cli/comfydock_cli/commands/base.py`

```python
from functools import cached_property
from abc import ABC

class BaseCommand(ABC):
    """Base class for all CLI command handlers."""

    @cached_property
    def workspace(self) -> "Workspace":
        """Get workspace instance. Exits if not initialized."""
        from ..cli_utils import get_workspace_or_exit
        return get_workspace_or_exit()
```

**Benefits**:
- Eliminates duplicate workspace initialization
- Central place for shared command utilities
- Enables future cross-cutting concerns (telemetry, etc.)

**Files to Modify**:
- `env_commands.py` - Inherit from BaseCommand, remove workspace property
- `global_commands.py` - Inherit from BaseCommand, remove workspace property

**Testing**:
- Update existing tests to work with inheritance
- Add test for workspace caching behavior

---

#### Task 3.2: Refactor Command Classes
**Modified Files**:
- `packages/cli/comfydock_cli/env_commands.py`
- `packages/cli/comfydock_cli/global_commands.py`

**Changes**:
```python
# Before
class EnvironmentCommands:
    def __init__(self):
        pass

    @cached_property
    def workspace(self) -> Workspace:
        return get_workspace_or_exit()

# After
from .commands.base import BaseCommand

class EnvironmentCommands(BaseCommand):
    def __init__(self):
        super().__init__()
```

**Apply Error Handler**:
```python
# Before
@with_env_logging("env create")
def create(self, args, logger=None):
    try:
        self.workspace.create_environment(...)
    except Exception as e:
        if logger:
            logger.error(f"Failed: {e}", exc_info=True)
        print(f"✗ Failed: {e}", file=sys.stderr)
        sys.exit(1)

# After
from ..utils.errors import handle_command_error

@with_env_logging("env create")
@handle_command_error
def create(self, args, logger=None):
    self.workspace.create_environment(...)
```

**Testing**:
- Ensure all existing tests pass
- Verify error handling works with decorator
- Check logger integration

---

### Phase 4: Progress and Callbacks (Week 4) 🟡 MEDIUM PRIORITY

#### Task 4.1: Create Progress Callback Factory
**New File**: `packages/cli/comfydock_cli/ui/progress_factory.py`

```python
from comfydock_core.models.workflow import NodeInstallCallbacks, BatchDownloadCallbacks
from comfydock_core.models.protocols import ImportCallbacks, ExportCallbacks

class ProgressCallbackFactory:
    """Factory for creating standard CLI progress callbacks."""

    @staticmethod
    def create_node_install_callbacks() -> NodeInstallCallbacks:
        """Create callbacks for node installation progress."""

    @staticmethod
    def create_model_download_callbacks() -> BatchDownloadCallbacks:
        """Create callbacks for model download progress."""

    @staticmethod
    def create_import_callbacks() -> ImportCallbacks:
        """Create callbacks for environment import progress."""

    @staticmethod
    def create_export_callbacks() -> ExportCallbacks:
        """Create callbacks for environment export progress."""
```

**Benefits**:
- Removes 120+ lines of inline callback definitions
- Consistent progress display across operations
- Single place to enhance progress UX

**Files to Modify**:
- `env_commands.py:898-928` - Use factory for node callbacks
- `env_commands.py:914-928` - Use factory for model callbacks
- `global_commands.py:198-261` - Use factory for import callbacks
- `global_commands.py:327-334` - Use factory for export callbacks

**Testing**:
- Create `tests/ui/test_progress_factory.py`
- Test each callback type
- Mock actual operations to verify callback invocation

---

### Phase 5: Polish and Optimization (Week 5) 🟢 OPTIONAL

#### Task 5.1: Extract Common Validators
**New File**: `packages/cli/comfydock_cli/utils/validation.py`

```python
from pathlib import Path

class CLIValidators:
    """Input validation utilities for CLI."""

    @staticmethod
    def validate_environment_name(name: str) -> tuple[bool, str | None]:
        """Validate environment name. Returns (is_valid, error_message)."""

    @staticmethod
    def validate_path(path: Path, must_exist: bool = False) -> tuple[bool, str | None]:
        """Validate file/directory path."""

    @staticmethod
    def validate_url(url: str) -> tuple[bool, str | None]:
        """Validate URL format."""
```

**Benefits**:
- Consistent validation across commands
- Better error messages
- Reusable validation logic

**Files to Modify**:
- `env_commands.py` - Use for environment name validation
- `global_commands.py` - Use for path/URL validation

---

#### Task 5.2: Create Output Formatting Utilities
**New File**: `packages/cli/comfydock_cli/ui/formatters.py`

```python
class CLIFormatters:
    """Output formatting utilities for consistent CLI display."""

    # Icons/Emojis
    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "⚠️"
    INFO = "ℹ️"

    @staticmethod
    def format_size(bytes: int) -> str:
        """Format file size in human-readable format."""

    @staticmethod
    def format_path(path: Path, max_length: int = 60) -> str:
        """Format path with truncation if needed."""

    @staticmethod
    def format_list(items: list, max_items: int = 5) -> str:
        """Format list with '... and N more' truncation."""
```

**Benefits**:
- Consistent formatting across all commands
- Single place to adjust display preferences
- Easier to add color/styling later

**Files to Modify**:
- Multiple locations across `env_commands.py` and `global_commands.py`
- Status display methods

---

## Implementation Order & Dependencies

```
Phase 1 (Foundation) - Required First
├── Task 1.1: Error Handler ━━━ No dependencies
├── Task 1.2: CLI Prompts ━━━━━ No dependencies
└── Task 1.3: Directory Setup ━ No dependencies

Phase 2 (Interactivity) - Requires Phase 1
├── Task 2.1: Pagination ━━━━━ Requires: 1.2 (prompts)
└── Task 2.2: Search Results ━ Requires: 1.2 (prompts), 2.1 (pagination)

Phase 3 (Architecture) - Requires Phase 1
├── Task 3.1: Base Command ━━━ Requires: 1.1 (error handler)
└── Task 3.2: Refactor Classes ━ Requires: 3.1 (base command)

Phase 4 (Progress) - Independent
└── Task 4.1: Callback Factory ━ No dependencies

Phase 5 (Polish) - Optional
├── Task 5.1: Validators ━━━━━ No dependencies
└── Task 5.2: Formatters ━━━━━ No dependencies
```

---

## Testing Strategy

### Test Coverage Requirements
- **New utilities**: 90%+ coverage required
- **Refactored code**: Maintain existing coverage
- **Integration tests**: Add end-to-end CLI tests

### Test Files to Create
```
packages/cli/tests/
├── utils/
│   ├── test_errors.py (Phase 1)
│   └── test_validation.py (Phase 5)
├── ui/
│   ├── test_prompts.py (Phase 1)
│   ├── test_pagination.py (Phase 2)
│   ├── test_search_results.py (Phase 2)
│   └── test_progress_factory.py (Phase 4)
└── commands/
    └── test_base_command.py (Phase 3)
```

### Regression Testing
- Run full test suite after each phase
- Manually test interactive flows (node add, workflow resolve)
- Verify error messages remain helpful

---

## Risk Assessment

### High Risk Areas
1. **Error handler decorator stacking** - Interaction with `@with_env_logging`
2. **Input mocking in tests** - Need clean way to mock `input()` calls
3. **Backward compatibility** - Some output format changes may surprise users

### Mitigation Strategies
1. **Incremental rollout** - One phase at a time with testing
2. **Feature flags** - Consider environment variable to enable/disable new UI
3. **Documentation** - Update CLI docs with any behavior changes

### Rollback Plan
- Each phase is independently reversible via git
- Keep old code commented for first few releases
- Monitor for user-reported issues

---

## Success Metrics

### Quantitative
- **Code reduction**: 500-700 lines removed
- **Test coverage**: Maintain or improve current coverage
- **File size reduction**:
  - `env_commands.py`: 1322 → ~1000 lines (24% reduction)
  - `interactive.py`: 830 → ~600 lines (28% reduction)

### Qualitative
- **Maintainability**: Easier to add new commands
- **Consistency**: Uniform UX across all commands
- **Testability**: Better mocking and unit test isolation

---

## Future Enhancements (Post-Refactor)

These are intentionally out of scope but become easier after refactoring:

1. **Rich UI Library** - Could swap `print()` for `rich` library with minimal changes
2. **Command Result Objects** - Return structured results instead of direct printing
3. **Telemetry** - Add analytics at BaseCommand level
4. **Progress Bars** - Enhanced progress display via factory
5. **Input History** - Add readline support in CLIPrompts
6. **CLI Testing Framework** - Build proper CLI test harness

---

## File References for Implementation

### Files to Read (Context)
```
packages/cli/comfydock_cli/env_commands.py:1-1322
packages/cli/comfydock_cli/global_commands.py:1-1064
packages/cli/comfydock_cli/cli.py:1-339
packages/cli/comfydock_cli/strategies/interactive.py:1-830
packages/cli/comfydock_cli/strategies/rollback.py:1-41
packages/cli/comfydock_cli/cli_utils.py (full file)
packages/cli/comfydock_cli/logging/environment_logger.py (for decorator interaction)
packages/cli/tests/conftest.py (for test setup)
```

### Files to Create
```
packages/cli/comfydock_cli/ui/__init__.py
packages/cli/comfydock_cli/ui/prompts.py
packages/cli/comfydock_cli/ui/pagination.py
packages/cli/comfydock_cli/ui/search_results.py
packages/cli/comfydock_cli/ui/progress_factory.py
packages/cli/comfydock_cli/ui/formatters.py
packages/cli/comfydock_cli/utils/errors.py
packages/cli/comfydock_cli/utils/validation.py
packages/cli/comfydock_cli/commands/__init__.py
packages/cli/comfydock_cli/commands/base.py
packages/cli/tests/utils/test_errors.py
packages/cli/tests/ui/test_prompts.py
packages/cli/tests/ui/test_pagination.py
packages/cli/tests/ui/test_search_results.py
packages/cli/tests/ui/test_progress_factory.py
packages/cli/tests/commands/test_base_command.py
```

### Files to Modify
```
packages/cli/comfydock_cli/env_commands.py (major refactor)
packages/cli/comfydock_cli/global_commands.py (major refactor)
packages/cli/comfydock_cli/strategies/interactive.py (major refactor)
packages/cli/comfydock_cli/cli.py (minor - import updates)
```

---

## Questions for Review

1. **Scope**: Is 5-week timeline acceptable, or should we prioritize subset?
2. **Testing**: What's acceptable test coverage threshold during refactor?
3. **UX Changes**: Any output format changes that would break user workflows?
4. **Dependencies**: Can we add any light UI libraries (e.g., `rich`), or pure stdlib only?
5. **Rollout**: Should we put refactor behind feature flag initially?

---

## Next Session Checklist

To implement this plan in the next session, you'll need:

- [ ] Approve overall phasing approach
- [ ] Confirm Phase 1 as starting point (error handler + prompts)
- [ ] Review CLIPrompts API design (matches your UX preferences?)
- [ ] Confirm test coverage expectations
- [ ] Decide on any additional context files to read

**Recommended Starting Point**: Task 1.1 (Error Handler) - lowest risk, highest immediate value.
