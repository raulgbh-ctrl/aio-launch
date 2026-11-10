import QtQuick
import QtQuick.Controls.Basic

Slider {
    id: s
    required property var theme
    implicitHeight: 28
    background: Rectangle {
        x: s.leftPadding
        y: s.topPadding + s.availableHeight / 2 - height / 2
        width: s.availableWidth; height: 5; radius: 3
        color: s.theme.surfaceContainerHighest
        Rectangle { width: s.visualPosition * parent.width; height: parent.height; radius: 3; color: s.theme.primary }
    }
    handle: Rectangle {
        x: s.leftPadding + s.visualPosition * (s.availableWidth - width)
        y: s.topPadding + s.availableHeight / 2 - height / 2
        width: 18; height: 18; radius: 9
        color: s.theme.primary
        border.width: s.pressed || s.visualFocus ? 3 : 0
        border.color: s.theme.primaryContainer
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
}
