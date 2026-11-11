import QtQuick

// The Cornerplay name, from the logo artwork: "Corner" in the text colour, "Play" in the
// accent, both following the theme (and so the wallpaper). The mark sits before it.
Row {
    id: wm
    property int size: 22                    // roughly the letters' height in pixels
    property bool showIcon: true
    property color ink: app.theme.onSurface
    property color accent: app.theme.primary  // the wallpaper's accent, grey included
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
