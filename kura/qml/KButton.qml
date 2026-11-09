import QtQuick
import QtQuick.Controls.Basic

Button {
    id: b
    required property var theme
    property bool primary: false
    property bool danger: false
    implicitHeight: 38
    leftPadding: 18; rightPadding: 18
    font.pixelSize: 13
    font.weight: Font.DemiBold
    contentItem: Text {
        text: b.text
        font: b.font
        color: !b.enabled ? b.theme.outline : b.primary ? b.theme.onPrimary : b.danger ? b.theme.error : b.theme.onSurface
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 10
        color: b.primary ? (b.enabled ? b.theme.primary : b.theme.surfaceContainerHighest)
                         : (b.hovered ? b.theme.surfaceContainerHighest : b.theme.surfaceContainerHigh)
        opacity: b.down ? 0.8 : b.hovered && b.primary ? 0.92 : 1
        border.width: b.visualFocus ? 2 : 0
        border.color: b.theme.outline
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
}
