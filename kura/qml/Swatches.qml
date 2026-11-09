import QtQuick
import QtQuick.Layouts

// A row of colour dots plus a hex field.
RowLayout {
    id: sw
    required property var theme
    property var choices: []
    property string value: ""
    signal picked(string colour)
    spacing: 8
    Repeater {
        model: sw.choices
        Rectangle {
            required property string modelData
            width: 26; height: 26; radius: 13
            color: modelData
            border.width: sw.value.toLowerCase() === modelData ? 3 : 1
            border.color: sw.value.toLowerCase() === modelData ? sw.theme.onSurface : sw.theme.outlineVariant
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: sw.picked(parent.modelData) }
        }
    }
    Item { Layout.fillWidth: true }
    KField {
        theme: sw.theme
        Layout.preferredWidth: 104
        text: sw.value
        maximumLength: 7
        font.family: "monospace"
        onEditingFinished: if (/^#[0-9a-fA-F]{6}$/.test(text)) sw.picked(text); else text = sw.value
    }
}
