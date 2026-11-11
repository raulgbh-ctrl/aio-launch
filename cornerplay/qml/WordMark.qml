import QtQuick

// The Cornerplay name, from the logo artwork: "Corner" in the text colour, "Play" in the
// accent, both following the theme (and so the wallpaper). The mark sits before it.
Row {
    id: wm
    property int size: 22                    // roughly the letters' height in pixels
    property bool showIcon: true
    property color ink: app.theme.onSurface
    // The wallpaper's accent; a colourless one (a grey wallpaper) falls back to the logo's orange.
    property color accent: app.theme.primary.hslSaturation > 0.18 ? app.theme.primary : "#ff9a3c"
    spacing: Math.round(size * 0.42)
    BrandMark {
        visible: wm.showIcon
        anchors.verticalCenter: parent.verticalCenter
        size: Math.round(wm.size * 1.6)
    }
    Item {
        anchors.verticalCenter: parent.verticalCenter
        height: Math.round(wm.size * 1.3)
        width: Math.round(height * 5.0756)   // the artwork's aspect
        BrandLayer { anchors.fill: parent; name: "wm-corner"; tint: wm.ink }
        BrandLayer { anchors.fill: parent; name: "wm-play"; tint: wm.accent }
    }
}
