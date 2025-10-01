"""Confirmation strategies for user interaction."""

from abc import ABC, abstractmethod


class ConfirmationStrategy(ABC):
    """Strategy for confirming user actions."""

    @abstractmethod
    def confirm_update(self, node_name: str, current_version: str, new_version: str) -> bool:
        """Ask user to confirm a node update.

        Args:
            node_name: Name of the node
            current_version: Current version
            new_version: New version

        Returns:
            True if user confirms, False otherwise
        """
        pass


class AutoConfirmStrategy(ConfirmationStrategy):
    """Always confirm without asking."""

    def confirm_update(self, node_name: str, current_version: str, new_version: str) -> bool:
        return True


class InteractiveConfirmStrategy(ConfirmationStrategy):
    """Ask user interactively via CLI."""

    def confirm_update(self, node_name: str, current_version: str, new_version: str) -> bool:
        response = input(
            f"Update '{node_name}' from {current_version} → {new_version}? (Y/n): "
        )
        return response.lower() != 'n'
