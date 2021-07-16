from __future__ import annotations

from PySide6.QtWidgets import QListWidget, QWidget  # Standard widgets.
from PySide6.QtGui import QPainter, QPaintEvent     # Standard GUI classes.
from PySide6.QtCore import Qt                       # Standard core classes.

###//### QListWidgetPlaceholder ###//###

class QListWidgetPlaceholder(QListWidget):
    """A QListWidget, with an additional placeholder component that is visible when there are zero items in the list.

    Credits: https://stackoverflow.com/a/60077423/7913061
    """

    def __init__(self, parent: QWidget = None, placeholder: str = '') -> None:
        super().__init__(parent)
        self._placeholder = placeholder

    @property
    def placeholder(self) -> str:
        return self._placeholder

    @placeholder.setter
    def placeholder(self, placeholder: str) -> None:
        self._placeholder = placeholder
        self.update()

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)

        # If there are no items in the list, draw the placeholder text instead.
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.save()
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(
                self.viewport().rect(),
                Qt.AlignCenter,
                self.fontMetrics().elidedText(self.placeholder, Qt.ElideRight, self.viewport().width())
            )
            painter.restore()
