import QtQuick
import QtQuick.Controls.Basic

// Drop-down over a list of {label, value} objects.
ComboBox {
    id: c
    required property var theme
    implicitHeight: 38
    textRole: "label"
    valueRole: "value"
    font.pixelSize: 13
    function select(value) {
        for (let i = 0; i < count; i++)
            if (model[i].value === value) { currentIndex = i; return }
        currentIndex = 0
    }
    contentItem: Text {
        leftPadding: 12; rightPadding: 30
        text: c.displayText
        font: c.font
        color: c.theme.onSurface
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: c.width - width - 12
        anchors.verticalCenter: parent.verticalCenter
        text: "▾"
        color: c.theme.onSurfaceVariant
        font.pixelSize: 13
    }
    background: Rectangle {
        radius: 10
        color: c.theme.surfaceContainerHigh
        border.width: c.activeFocus || c.popup.visible ? 2 : 1
        border.color: c.activeFocus || c.popup.visible ? c.theme.primary : c.theme.outlineVariant
    }
    delegate: ItemDelegate {
        id: row
        required property var modelData
        required property int index
        width: c.width - 8
        height: 34
        highlighted: c.highlightedIndex === index
        contentItem: Text {
            text: row.modelData.label
            color: c.currentIndex === row.index ? c.theme.primary : c.theme.onSurface
            font.pixelSize: 13
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { radius: 8; color: row.highlighted ? c.theme.surfaceContainerHighest : "transparent" }
    }
    popup: Popup {
        y: c.height + 4
        width: c.width
        padding: 4
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 280)
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: c.popup.visible ? c.delegateModel : null
            currentIndex: c.highlightedIndex
            ScrollBar.vertical: KScrollBar { }
        }
        background: Rectangle {
            radius: 10
            color: c.theme.surfaceContainerHigh
            border.width: 1
            border.color: c.theme.outlineVariant
        }
    }
}
