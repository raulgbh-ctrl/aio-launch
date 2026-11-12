import QtQuick
import QtQuick.Effects

// A game's own logo (transparent art) when one loads, otherwise its title in big type.
Item {
    id: lt
    property var logos: []
    property string title: ""
    property color color: "white"
    property int pixelSize: 36
    property int logoHeight: 96
    property int maxWidth: 520
    readonly property bool hasLogo: logo.status === Image.Ready
    implicitWidth: hasLogo ? Math.min(maxWidth, logo.paintedWidth) : Math.min(maxWidth, text.implicitWidth)
    implicitHeight: hasLogo ? logoHeight : text.implicitHeight

    ArtImage {
        id: logo
        anchors { left: parent.left; verticalCenter: parent.verticalCenter }
        width: lt.maxWidth
        height: lt.logoHeight
        sources: lt.logos || []
        fillMode: Image.PreserveAspectFit
        horizontalAlignment: Image.AlignLeft
        sourceSize.height: lt.logoHeight * 2
        opacity: status === Image.Ready ? 1 : 0
        Behavior on opacity { enabled: !app.light; NumberAnimation { duration: 220 } }
        // Most logos are white: a soft shadow keeps them readable on light themes and bright art.
        layer.enabled: status === Image.Ready && GraphicsInfo.api !== GraphicsInfo.Software
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "black"
            shadowOpacity: app.theme.dark === false ? 1.0 : 0.55
            shadowBlur: 0.35
            blurMax: 24
            shadowScale: 1.03
            shadowVerticalOffset: 2
            autoPaddingEnabled: true
        }
    }
    Text {
        id: text
        visible: !lt.hasLogo
        width: lt.maxWidth
        text: lt.title
        color: lt.color
        font.pixelSize: lt.pixelSize
        font.family: app.titleFamily
        font.weight: Font.Black
        wrapMode: Text.WordWrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }
}
