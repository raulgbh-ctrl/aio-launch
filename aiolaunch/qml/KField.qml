import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: f
    required property var theme
    implicitHeight: 38
    leftPadding: 12; rightPadding: 12
    font.pixelSize: 13
    color: theme.onSurface
    placeholderTextColor: theme.outline
    selectionColor: theme.primaryContainer
    selectedTextColor: theme.onPrimaryContainer
    selectByMouse: true
    background: Rectangle {
        radius: 10
        color: f.theme.surfaceContainerHigh
        border.width: f.activeFocus ? 2 : 1
        border.color: f.activeFocus ? f.theme.primary : f.theme.outlineVariant
    }
}
