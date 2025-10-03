"""Interactive resolution strategies for CLI."""

from typing import Optional, List

from comfydock_core.models.protocols import (
    NodeResolutionStrategy,
    ModelResolutionStrategy,
)
from comfydock_core.models.workflow import ResolvedNodePackage, WorkflowNodeWidgetRef
from comfydock_core.models.shared import ModelWithLocation


class InteractiveNodeStrategy(NodeResolutionStrategy):
    """Interactive node resolution with user prompts."""

    def resolve_unknown_node(
        self, node_type: str, possible: List[ResolvedNodePackage]
    ) -> ResolvedNodePackage | None:
        """Prompt user to resolve unknown node."""
        if not possible:
            print(f"⚠️  No registry matches found for '{node_type}'")
            print("  Options:")
            print("    s. Skip this node")
            print("    m. Enter package ID manually")

            choice = input("Choice [s]: ").strip().lower() or "s"
            if choice == "m":
                manual = input("Enter package ID: ").strip()
                if manual:
                    # TODO: Create a manual ResolvedNodePackage
                    # Note: This would need actual package data in production
                    print(f"  Note: Manual package '{manual}' will need to be verified")
                return None
            return None
        
        if len(possible) == 1:
            return possible[0]

        print(f"\n🔍 Found {len(possible)} matches for '{node_type}':")
        for i, pkg in enumerate(possible[:5], 1):
            display_name = pkg.package_data.display_name or pkg.package_id
            desc = pkg.package_data.description or "No description"
            confidence = pkg.match_confidence
            print(f"  {i}. {display_name} (confidence: {confidence:.1f})")
            if desc and len(desc) > 60:
                desc = desc[:57] + "..."
            print(f"      {desc}")
        print("  s. Skip this node")

        while True:
            choice = input("Choice [1/s]: ").strip().lower()
            if choice == "s":
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(possible[:5]):
                    return possible[idx]
            print("  Invalid choice, try again")

    def confirm_node_install(self, package: ResolvedNodePackage) -> bool:
        """Always confirm since user already made the choice."""
        return True


class InteractiveModelStrategy(ModelResolutionStrategy):
    """Interactive model resolution with user prompts."""

    def __init__(self, fuzzy_search_fn=None):
        """Initialize with optional fuzzy search function."""
        self.fuzzy_search_fn = fuzzy_search_fn

    def resolve_ambiguous_model(
        self, reference: WorkflowNodeWidgetRef, candidates: List[ModelWithLocation]
    ) -> Optional[ModelWithLocation]:
        """Prompt user to resolve ambiguous model."""
        print(f"\n🔍 Multiple matches for model in node #{reference.node_id}:")
        print(f"  Looking for: {reference.widget_value}")
        print("  Found matches:")

        for i, model in enumerate(candidates[:10], 1):
            size_mb = model.file_size / (1024 * 1024)
            print(f"  {i}. {model.relative_path} ({size_mb:.1f} MB)")
        print("  s. Skip")

        while True:
            choice = input("Choice [1/s]: ").strip().lower()
            if choice == "s":
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(candidates[:10]):
                    selected = candidates[idx]
                    print(f"  ✓ Selected: {selected.relative_path}")
                    return selected
            print("  Invalid choice, try again")

    def handle_missing_model(self, reference: WorkflowNodeWidgetRef) -> tuple[str, str] | None:
        """Prompt user for missing model."""
        print(f"\n⚠️  Model not found: {reference.widget_value}")
        print(f"  in node #{reference.node_id} ({reference.node_type})")

        # If we have fuzzy search, try it first
        if self.fuzzy_search_fn:
            print("\n🔍 Searching model index...")

            similar = self.fuzzy_search_fn(
                missing_ref=reference.widget_value,
                node_type=reference.node_type,
                limit=10
            )

            if similar:
                return self._show_fuzzy_results(reference, similar)
            else:
                print("  No similar models found in index")

        # Fallback to manual options
        print("\nOptions:")
        print("  1. Enter path manually")
        print("  2. Skip (resolve later)")

        while True:
            choice = input("\nChoice [2]: ").strip() or "2"

            if choice == "1":
                path = input("Enter model path: ").strip()
                if path:
                    return ("select", path)
                return ("skip", "")
            elif choice == "2":
                return ("skip", "")
            else:
                print("  Invalid choice, try again")

    def _show_fuzzy_results(self, reference: WorkflowNodeWidgetRef, results: List) -> tuple[str, str] | None:
        """Show fuzzy search results and get user selection."""
        print(f"\nFound {len(results)} potential matches:\n")

        # Show up to 5 results
        display_count = min(5, len(results))
        for i, match in enumerate(results[:display_count], 1):
            model = match.model
            size_gb = model.file_size / (1024 * 1024 * 1024)
            confidence = match.confidence.capitalize()
            print(f"  {i}. {model.relative_path} ({size_gb:.2f} GB)")
            print(f"     Hash: {model.hash[:12]}... | {confidence} confidence match\n")

        if len(results) > 5:
            print(f"  6. [Browse all {len(results)} matches...]\n")

        print("  0. Other options (manual path, skip)\n")

        while True:
            choice = input("Choice [1]: ").strip() or "1"

            if choice == "0":
                # Show other options
                print("\nOther options:")
                print("  1. Enter model path manually")
                print("  2. Skip (resolve later)")

                sub_choice = input("\nChoice [2]: ").strip() or "2"
                if sub_choice == "1":
                    path = input("Enter model path: ").strip()
                    if path:
                        return ("select", path)
                return ("skip", "")

            elif choice == "6" and len(results) > 5:
                # Browse all results
                selected = self._browse_all_models(results)
                if selected:
                    return ("select", selected.relative_path)
                return ("skip", "")

            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < display_count:
                    selected = results[idx].model
                    print(f"\n✓ Selected: {selected.relative_path}")
                    print(f"  Hash: {selected.hash[:12]}... | Size: {selected.file_size / (1024 * 1024 * 1024):.2f} GB")
                    return ("select", selected.relative_path)

            print("  Invalid choice, try again")

    def _browse_all_models(self, results: List) -> Optional:
        """Browse all fuzzy search results with pagination."""
        page = 0
        page_size = 10
        total_pages = (len(results) + page_size - 1) // page_size

        while True:
            start = page * page_size
            end = min(start + page_size, len(results))

            print(f"\nAll matches (Page {page + 1}/{total_pages}):\n")

            for i, match in enumerate(results[start:end], start + 1):
                model = match.model
                size_gb = model.file_size / (1024 * 1024 * 1024)
                print(f"  {i}. {model.relative_path} ({size_gb:.2f} GB)")

            print(f"\n[N]ext, [P]rev, or enter number (or [Q]uit):")

            choice = input("Choice: ").strip().lower()

            if choice == 'n' and page < total_pages - 1:
                page += 1
            elif choice == 'p' and page > 0:
                page -= 1
            elif choice == 'q':
                return None
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    return results[idx].model
            else:
                print("  Invalid choice, try again")


