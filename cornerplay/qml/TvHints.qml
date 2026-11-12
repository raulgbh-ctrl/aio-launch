import QtQuick

// The hint bar along the bottom of TV mode's pages: the controller's own button glyphs when a
// pad is connected (or on a Steam Deck), keycaps otherwise. hints: [{ b: "a", k: "Enter", t: "Choose" }];
// b "" or k "" leave out the glyph or the keycap (for "◂ ▸ earlier / later").
Row {
    id: bar
    required property var theme
    property var hints: []
    property real size: 26
    spacing: 26
    Repeater {
        model: bar.hints
        Row {
            required property var modelData
            readonly property bool usePad: pad.connected || pad.deck
            spacing: 8
            PadButton { visible: usePad && !!modelData.b; button: modelData.b || "a"; style: pad.style; size: bar.size }
            Rectangle {
                visible: !usePad && !!modelData.k
                anchors.verticalCenter: parent.verticalCenter
                height: bar.size; radius: 6
                width: cap.implicitWidth + 16
                color: Qt.alpha(bar.theme.surfaceContainerHighest, 0.9)
                border.width: 1; border.color: bar.theme.outlineVariant
                Text { id: cap; anchors.centerIn: parent; text: modelData.k || ""; color: bar.theme.onSurface
                       font.pixelSize: Math.round(bar.size * 0.46); font.weight: Font.DemiBold }
            }
            Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.t; color: bar.theme.onSurfaceVariant
                   font.pixelSize: Math.round(bar.size * 0.6) }
        }
    }
}
