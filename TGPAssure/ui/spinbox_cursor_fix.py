"""Application-wide cursor correction for Qt spin boxes.

Qt spin boxes are one widget with painted up/down button sub-controls. On some
Windows/Qt style combinations the text-editor I-beam cursor leaks over the
painted arrow-button area, so the user sees a text cursor on the step buttons.
This module installs one QApplication event filter that switches the cursor to
an arrow only while the pointer is over the spin-button sub-controls and keeps
normal text-edit behaviour in the value field.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QEvent, QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QLineEdit, QStyle, QStyleOptionSpinBox, QWidget


_SPINBOX_CURSOR_FILTER: Optional["SpinBoxCursorFilter"] = None


class SpinBoxCursorFilter(QObject):
    """Keeps spin-box arrows on an arrow cursor without breaking text editing."""

    _TRACKED_EVENT_TYPES = {
        QEvent.Type.Enter,
        QEvent.Type.Leave,
        QEvent.Type.MouseMove,
        QEvent.Type.HoverMove,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.MouseButtonRelease,
    }

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._last_spinbox: QAbstractSpinBox | None = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API name
        try:
            if event.type() == QEvent.Type.ChildAdded:
                child = getattr(event, "child", lambda: None)()
                if isinstance(child, QWidget):
                    self._prepare_spinbox_tree(child)
                return False

            spinbox = self._resolve_spinbox(watched)
            if spinbox is None or event.type() not in self._TRACKED_EVENT_TYPES:
                return False

            if event.type() == QEvent.Type.Leave:
                if spinbox is self._last_spinbox:
                    self._last_spinbox = None
                self._set_default_cursor(spinbox)
                return False

            local_pos = self._event_position_in_spinbox(watched, event, spinbox)
            if local_pos is None:
                return False

            if self._is_over_step_button(spinbox, local_pos):
                self._last_spinbox = spinbox
                spinbox.setCursor(Qt.CursorShape.ArrowCursor)
                line_edit = spinbox.findChild(QLineEdit)
                if line_edit is not None:
                    line_edit.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self._set_default_cursor(spinbox)
        except RuntimeError:
            # Widget was deleted while Qt was dispatching the event.
            self._last_spinbox = None
        except Exception:
            # Cursor polish must never block normal widget behaviour.
            pass
        return False

    def _resolve_spinbox(self, watched: QObject) -> QAbstractSpinBox | None:
        if isinstance(watched, QAbstractSpinBox):
            return watched
        if isinstance(watched, QLineEdit):
            parent = watched.parentWidget()
            if isinstance(parent, QAbstractSpinBox):
                return parent
        return None

    def _event_position_in_spinbox(
        self,
        watched: QObject,
        event: QEvent,
        spinbox: QAbstractSpinBox,
    ) -> QPoint | None:
        position = None
        if hasattr(event, "position"):
            position = event.position().toPoint()
        elif hasattr(event, "pos"):
            position = event.pos()
        if position is None:
            global_pos = QCursor.pos()
            return spinbox.mapFromGlobal(global_pos)
        if watched is spinbox:
            return position
        if isinstance(watched, QWidget):
            return spinbox.mapFromGlobal(watched.mapToGlobal(position))
        return None

    def _is_over_step_button(self, spinbox: QAbstractSpinBox, pos: QPoint) -> bool:
        option = QStyleOptionSpinBox()
        try:
            spinbox.initStyleOption(option)
            up_rect = spinbox.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox,
                option,
                QStyle.SubControl.SC_SpinBoxUp,
                spinbox,
            )
            down_rect = spinbox.style().subControlRect(
                QStyle.ComplexControl.CC_SpinBox,
                option,
                QStyle.SubControl.SC_SpinBoxDown,
                spinbox,
            )
            return up_rect.contains(pos) or down_rect.contains(pos)
        except Exception:
            # Safe fallback: most spin-box buttons occupy the right-side button strip.
            button_width = max(18, min(34, spinbox.height()))
            return pos.x() >= spinbox.width() - button_width

    def _set_default_cursor(self, spinbox: QAbstractSpinBox) -> None:
        spinbox.unsetCursor()
        line_edit = spinbox.findChild(QLineEdit)
        if line_edit is not None:
            line_edit.setCursor(Qt.CursorShape.IBeamCursor)

    def _prepare_spinbox_tree(self, widget: QWidget) -> None:
        targets: list[QAbstractSpinBox] = []
        if isinstance(widget, QAbstractSpinBox):
            targets.append(widget)
        targets.extend(widget.findChildren(QAbstractSpinBox))
        for spinbox in targets:
            spinbox.setMouseTracking(True)
            spinbox.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            line_edit = spinbox.findChild(QLineEdit)
            if line_edit is not None:
                line_edit.setMouseTracking(True)
                line_edit.setCursor(Qt.CursorShape.IBeamCursor)



def install_spinbox_cursor_fix(app: QApplication | None = None) -> SpinBoxCursorFilter | None:
    """Install the global spin-box cursor fix once and return the filter."""

    global _SPINBOX_CURSOR_FILTER
    if _SPINBOX_CURSOR_FILTER is not None:
        return _SPINBOX_CURSOR_FILTER

    app = app or QApplication.instance()
    if app is None:
        return None

    cursor_filter = SpinBoxCursorFilter(app)
    app.installEventFilter(cursor_filter)
    for widget in app.allWidgets():
        cursor_filter._prepare_spinbox_tree(widget)
    _SPINBOX_CURSOR_FILTER = cursor_filter
    return cursor_filter
