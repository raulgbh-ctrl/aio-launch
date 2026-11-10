import QtQuick
import QtQuick.Controls.Basic

Popup {
    id: d
    required property var theme
    property string heading: ""
    property string headingIcon: ""   // optional icon before the heading
    parent: Overlay.overlay
    // Centred, plus a small rise that the opening animation brings to 0 (it slides up).
    property real rise: 0
    x: Math.round((parent ? parent.width - width : 0) / 2)
    y: Math.round((parent ? parent.height - height : 0) / 2 + rise)
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
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180; easing.type: Easing.OutCubic }
        NumberAnimation { property: "rise"; from: 36; to: 0; duration: 280; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: 280; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        enabled: !app.light
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 120 }
        NumberAnimation { property: "rise"; from: 0; to: 18; duration: 120 }
    }
}
