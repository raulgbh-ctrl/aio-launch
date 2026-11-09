import QtQuick
import QtQuick.Controls.Basic

Popup {
    id: d
    required property var theme
    property string heading: ""
    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    padding: 24
    topPadding: 64
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    Overlay.modal: Rectangle { color: "#99000000" }
    background: Rectangle {
        radius: 18
        color: d.theme.surfaceContainer
        border.width: 1
        border.color: d.theme.outlineVariant
        Text {
            x: 24; y: 22
            text: d.heading
            color: d.theme.onSurface
            font.pixelSize: 18
            font.weight: Font.DemiBold
        }
        Text {
            anchors { right: parent.right; top: parent.top; margins: 18 }
            text: "✕"
            color: d.theme.onSurfaceVariant
            font.pixelSize: 16
            TapHandler { onTapped: d.close() }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
        }
    }
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120 } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 90 } }
}
