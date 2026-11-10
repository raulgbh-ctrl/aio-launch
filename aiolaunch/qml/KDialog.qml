import QtQuick
import QtQuick.Controls.Basic

Popup {
    id: d
    required property var theme
    property string heading: ""
    property string headingIcon: ""   // optional icon before the heading
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
        Icon {
            visible: d.headingIcon !== "" && d.heading !== ""
            x: 24; y: 25
            name: d.headingIcon; size: 20
            color: d.theme.primary
        }
        Text {
            x: d.headingIcon ? 54 : 24; y: 22
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
    enter: Transition {
        enabled: !app.light
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 160; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.95; to: 1; duration: 220; easing.type: Easing.OutBack; easing.overshoot: 1.2 }
    }
    exit: Transition {
        enabled: !app.light
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 110 }
        NumberAnimation { property: "scale"; from: 1; to: 0.97; duration: 110 }
    }
}
