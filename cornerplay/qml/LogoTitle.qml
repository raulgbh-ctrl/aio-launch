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

    // Light themes: a soft dark cloud behind the logo, so white logos read on pale art and
    // coloured ones still keep their colours.
    RectangularShadow {
        visible: lt.hasLogo && app.theme.dark === false && GraphicsInfo.api !== GraphicsInfo.Software
        x: -logo.paintedWidth * 0.04
        anchors.verticalCenter: logo.verticalCenter
        width: logo.paintedWidth * 1.08
        height: logo.paintedHeight * 0.86
        radius: height / 2
        blur: Math.max(24, height * 0.6)
        color: Qt.alpha("black", 0.55)
    }
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
            // On a light theme the shadow is wider and darker, a soft dark halo the white letters sit on.
            shadowOpacity: app.theme.dark === false ? 0.9 : 0.55
            shadowBlur: app.theme.dark === false ? 0.7 : 0.35
            blurMax: app.theme.dark === false ? 40 : 24
            shadowScale: app.theme.dark === false ? 1.06 : 1.03
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
