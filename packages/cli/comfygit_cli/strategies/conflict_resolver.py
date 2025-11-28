"""Conflict resolution strategies for pull/merge operations."""

from typing import Literal

from comfygit_core.models.ref_diff import (
    DependencyConflict,
    NodeConflict,
    RefDiff,
    WorkflowConflict,
)

Resolution = Literal["take_base", "take_target", "skip"]


class InteractiveConflictResolver:
    """CLI interactive conflict resolver.

    Prompts user for each conflict detected before a merge/pull.
    """

    def resolve_workflow(self, conflict: WorkflowConflict) -> Resolution:
        """Prompt user to resolve a workflow conflict."""
        print(f"\nWorkflow conflict: {conflict.identifier}")
        print(f"  Your version:   {conflict.base_hash or 'unknown'}")
        print(f"  Their version:  {conflict.target_hash or 'unknown'}")
        print()
        print("  [m] Keep mine (your version)")
        print("  [t] Keep theirs (incoming)")
        print("  [s] Skip (resolve later)")

        while True:
            choice = input("  > ").lower().strip()
            if choice == "m":
                return "take_base"
            elif choice == "t":
                return "take_target"
            elif choice == "s":
                return "skip"
            print("  Invalid choice. Enter m, t, or s.")

    def resolve_node(self, conflict: NodeConflict) -> Resolution:
        """Prompt user to resolve a node version conflict."""
        print(f"\nNode conflict: {conflict.identifier}")
        if conflict.conflict_type == "delete_modify":
            if conflict.target_deleted:
                print(f"  Your version:   {conflict.base_version}")
                print("  Their version:  (deleted)")
            else:
                print("  Your version:   (deleted)")
                print(f"  Their version:  {conflict.target_version}")
        else:
            print(f"  Your version:   {conflict.base_version}")
            print(f"  Their version:  {conflict.target_version}")
        print()
        print("  [m] Keep mine (your version)")
        print("  [t] Keep theirs (incoming)")
        print("  [s] Skip (resolve later)")

        while True:
            choice = input("  > ").lower().strip()
            if choice == "m":
                return "take_base"
            elif choice == "t":
                return "take_target"
            elif choice == "s":
                return "skip"
            print("  Invalid choice. Enter m, t, or s.")

    def resolve_dependency(self, conflict: DependencyConflict) -> Resolution:
        """Prompt user to resolve a dependency conflict."""
        print(f"\nDependency conflict: {conflict.identifier}")
        print(f"  Your version:   {conflict.base_spec or 'unknown'}")
        print(f"  Their version:  {conflict.target_spec or 'unknown'}")
        print()
        print("  [m] Keep mine (your version)")
        print("  [t] Keep theirs (incoming)")
        print("  [s] Skip (resolve later)")

        while True:
            choice = input("  > ").lower().strip()
            if choice == "m":
                return "take_base"
            elif choice == "t":
                return "take_target"
            elif choice == "s":
                return "skip"
            print("  Invalid choice. Enter m, t, or s.")

    def resolve_all(self, diff: RefDiff) -> dict[str, Resolution]:
        """Resolve all conflicts in a diff interactively.

        Args:
            diff: RefDiff with conflicts

        Returns:
            Dict mapping conflict identifiers to resolutions
        """
        resolutions: dict[str, Resolution] = {}

        if not diff.has_conflicts:
            return resolutions

        print("\n=== Conflict Resolution ===")
        print(f"Found {len(diff.all_conflicts)} conflict(s) to resolve.\n")

        for conflict in diff.all_conflicts:
            if conflict.resolution != "unresolved":
                continue

            if isinstance(conflict, WorkflowConflict):
                resolution = self.resolve_workflow(conflict)
            elif isinstance(conflict, NodeConflict):
                resolution = self.resolve_node(conflict)
            elif isinstance(conflict, DependencyConflict):
                resolution = self.resolve_dependency(conflict)
            else:
                continue

            resolutions[conflict.identifier] = resolution
            # Only update the conflict's resolution if not skipped
            if resolution != "skip":
                conflict.resolution = resolution  # type: ignore[assignment]

        return resolutions


class AutoConflictResolver:
    """Auto-resolve conflicts using a fixed strategy.

    Used with --auto-resolve flag for non-interactive resolution.
    """

    def __init__(self, strategy: Literal["mine", "theirs"]):
        """Initialize with resolution strategy.

        Args:
            strategy: "mine" to keep local, "theirs" to take incoming
        """
        self._resolution: Resolution = (
            "take_base" if strategy == "mine" else "take_target"
        )

    def resolve_workflow(self, conflict: WorkflowConflict) -> Resolution:
        return self._resolution

    def resolve_node(self, conflict: NodeConflict) -> Resolution:
        return self._resolution

    def resolve_dependency(self, conflict: DependencyConflict) -> Resolution:
        return self._resolution

    def resolve_all(self, diff: RefDiff) -> dict[str, Resolution]:
        """Auto-resolve all conflicts.

        Args:
            diff: RefDiff with conflicts

        Returns:
            Dict mapping conflict identifiers to resolutions
        """
        resolutions: dict[str, Resolution] = {}

        for conflict in diff.all_conflicts:
            if conflict.resolution != "unresolved":
                continue

            resolutions[conflict.identifier] = self._resolution
            conflict.resolution = self._resolution  # type: ignore[assignment]

        return resolutions
