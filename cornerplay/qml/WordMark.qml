import QtQuick

// The Cornerplay name: "Corner" in Outfit, "play" bold in the signature colour, after the icon.
Row {
    id: wm
    property int size: 22                    // text height in pixels
    property bool showIcon: true
    property color ink: app.theme.onSurface
    property color accent: app.theme.primary  // amber in the Cornerplay theme
    spacing: Math.round(size * 0.42)
    Image {
        visible: wm.showIcon
        anchors.verticalCenter: parent.verticalCenter
        source: "../cornerplay.svg"
        width: Math.round(wm.size * 1.6); height: width
        sourceSize: Qt.size(Math.ceil(width * Math.max(2, Screen.devicePixelRatio)), Math.ceil(height * Math.max(2, Screen.devicePixelRatio)))
        smooth: true
    }
    Row {
        anchors.verticalCenter: parent.verticalCenter
        // Outfit is a variable font: the weight is set on its "wght" axis (font.weight alone picks its thinnest).
        Text { text: "Corner"; color: wm.ink; font.family: "Outfit"; font.pixelSize: wm.size; font.weight: Font.Medium
               font.variableAxes: ({ "wght": 460 }); font.letterSpacing: -0.3 }
        Text { text: "play"; color: wm.accent; font.family: "Outfit"; font.pixelSize: wm.size; font.weight: Font.Bold
               font.variableAxes: ({ "wght": 720 }); font.letterSpacing: -0.3 }
    }
}
