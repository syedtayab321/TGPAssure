from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QObject, QPoint, QRect


def fade_widget(widget, start=0.0, end=1.0, duration=300):
    animation = QPropertyAnimation(widget, b'windowOpacity', widget)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setDuration(duration)
    animation.setEasingCurve(QEasingCurve.InOutCubic)
    animation.start()
    return animation


def slide_widget(widget, start_rect, end_rect, duration=300):
    animation = QPropertyAnimation(widget, b'geometry', widget)
    animation.setStartValue(QRect(*start_rect))
    animation.setEndValue(QRect(*end_rect))
    animation.setDuration(duration)
    animation.setEasingCurve(QEasingCurve.InOutCubic)
    animation.start()
    return animation
