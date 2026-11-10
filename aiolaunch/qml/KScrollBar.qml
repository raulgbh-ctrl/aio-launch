import QtQuick
import QtQuick.Controls.Basic

// A slim scrollbar: a thin pill that widens and takes the accent colour when used.
ScrollBar {
    id: sb
    readonly property var theme: app.theme
    implicitWidth: hovered || pressed ? 10 : 6
    Behavior on implicitWidth { enabled: !app.light; NumberAnimation { duration: 120 } }
    padding: 2
    background: Item { }
    contentItem: Rectangle {
        radius: width / 2
        color: sb.pressed ? sb.theme.primary : sb.hovered ? Qt.alpha(sb.theme.primary, 0.8) : Qt.alpha(sb.theme.onSurface, 0.28)
        opacity: sb.active || sb.hovered ? 1 : 0.35
        Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 250 } }
        Behavior on color { enabled: !app.light; ColorAnimation { duration: 150 } }
    }
}
