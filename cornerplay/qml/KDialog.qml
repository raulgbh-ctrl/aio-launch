import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

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
    // Behind the pop-up the app goes soft and dim, like frosted glass (the main window names
    // what to blur as blurTarget; without it, or without a GPU, it just dims).
    readonly property Item blurTarget: ApplicationWindow.window ? ApplicationWindow.window.blurTarget || null : null
    Overlay.modal: Item {
        MultiEffect {
            anchors.fill: parent
            visible: !!d.blurTarget && !app.light && GraphicsInfo.api !== GraphicsInfo.Software
            source: visible ? d.blurTarget : null
            autoPaddingEnabled: false
            blurEnabled: true; blur: 0.8; blurMax: 48
        }
        // Dark themes dim; light ones get a soft veil instead of turning grey.
        Rectangle { anchors.fill: parent; color: d.theme.dark === false ? Qt.alpha(d.theme.onSurface, 0.16) : Qt.alpha("black", 0.5) }
    }
    background: Rectangle {
        radius: 22
        color: Qt.alpha(d.theme.surfaceContainer, 0.96)
        border.width: 1
        border.color: d.theme.dark === false ? Qt.alpha("black", 0.08) : Qt.alpha("white", 0.08)
        RectangularShadow {
            z: -1
            anchors.fill: parent
            visible: !app.light && GraphicsInfo.api !== GraphicsInfo.Software
            radius: parent.radius
            blur: 48; offset.y: 18
            color: Qt.alpha("black", 0.45)
        }
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
            font.pixelSize: 19
            font.weight: Font.Bold
        }
        Rectangle {  // close: a round button
            anchors { right: parent.right; top: parent.top; margins: 16 }
            width: 32; height: 32; radius: 16
            color: closeHover.hovered ? d.theme.surfaceContainerHighest : Qt.alpha(d.theme.surfaceContainerHigh, 0.8)
            Behavior on color { ColorAnimation { duration: 120 } }
            Icon { anchors.centerIn: parent; name: "x"; size: 16; color: d.theme.onSurfaceVariant }
            HoverHandler { id: closeHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: d.close() }
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
